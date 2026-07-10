import mysql.connector
import logging
from db.database import get_connection
from datetime import datetime
import time

# Deduct butterflies

def deduct_butterflies(user_id, cost):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET butterflies = butterflies - %s WHERE discord_id = %s", (cost, user_id))
    conn.commit()
    conn.close()

# Insert into purchase history

def insert_purchase_history(user_id, item_id, cost):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO purchase_history (user_discord_id, item_id, quantity, cost, purchased_at)
        VALUES (%s, %s, 1, %s, %s)
    """, (user_id, item_id, cost, datetime.utcnow()))
    conn.commit()
    conn.close()

# Thread-safe inventory insert with lock cleanup

def threaded_grant_item(user_id: int, item_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Kill blockers on `user_inventory`
        cursor.execute("SHOW PROCESSLIST")
        for row in cursor.fetchall():
            pid, user, host, db, command, time, state, info = row[:8]
            if db == 'kitty_kingdom' and 'user_inventory' in str(info).lower() and pid != conn.connection_id:
                try:
                    kill_cursor = conn.cursor()
                    kill_cursor.execute(f"KILL {pid}")
                    logging.warning(f"Killed blocking process {pid} on user_inventory")
                except Exception as e:
                    logging.error(f"Failed to kill process {pid}: {e}")

        # Grant item
        cursor.execute("""
            INSERT INTO user_inventory (user_discord_id, item_id, quantity, acquired_at)
            VALUES (%s, %s, 1, %s)
            ON DUPLICATE KEY UPDATE quantity = quantity + 1, acquired_at = %s
        """, (user_id, item_id, datetime.utcnow(), datetime.utcnow()))

        conn.commit()
        logging.info(f"✅ Granted item {item_id} to user {user_id}")

    except Exception as e:
        logging.error(f"[GRANT ITEM ERROR] {e}", exc_info=True)
        raise
    finally:
        conn.close()


def kill_locks_and_insert_inventory(user_id, item_id, acquired_at):
    try:
        logging.debug("🔍 Checking for blocking locks on `user_inventory`...")
        conn_kill = get_connection()
        cursor_kill = conn_kill.cursor()

        cursor_kill.execute("SHOW PROCESSLIST")
        processes = cursor_kill.fetchall()

        for row in processes:
            pid, user, host, db, command, time_alive, state, info = row[:8]
            if db == 'kitty_kingdom' and 'user_inventory' in str(info).lower() and command in ('Query', 'Sleep'):
                if pid != conn_kill.connection_id:
                    logging.warning(f"⛔ Killing blocking process ID {pid} (Info: {info})")
                    try:
                        cursor_kill.execute(f"KILL {pid}")
                    except Exception as e:
                        logging.error(f"❌ Could not kill process {pid}: {e}")

        conn_kill.close()

        # Step 2: Insert in a fresh connection after brief delay
        retries = 5
        while retries > 0:
            try:
                conn_insert = get_connection()
                cursor_insert = conn_insert.cursor()
                cursor_insert.execute("""
                    INSERT INTO user_inventory (user_discord_id, item_id, quantity, acquired_at)
                    VALUES (%s, %s, 1, %s)
                    ON DUPLICATE KEY UPDATE quantity = quantity + 1, acquired_at = %s
                """, (user_id, item_id, acquired_at, acquired_at))
                conn_insert.commit()
                conn_insert.close()
                logging.debug("✅ Successfully inserted inventory after killing locks.")
                return
            except mysql.connector.Error as err:
                logging.warning(f"⏳ Retry needed: {err}")
                retries -= 1
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"🔥 Failed during insert retry: {e}")
                break

    except Exception as e:
        logging.error(f"[THREAD-SQL-HANDLER ERROR] {e}", exc_info=True)
