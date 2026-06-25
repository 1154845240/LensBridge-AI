import sqlite3
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app_paths

app_paths.ensure_runtime_layout()
DB_PATH = str(app_paths.DB_PATH)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Check if captures table exists and check if conversation_id column is present
    try:
        cursor.execute("SELECT conversation_id FROM captures LIMIT 1")
    except sqlite3.OperationalError:
        # Table does not exist, or conversation_id column is missing
        # Drop table if exists to recreate with foreign key
        cursor.execute("DROP TABLE IF EXISTS captures")
        
    # 3. Create captures table with conversation_id
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            image_filename TEXT NOT NULL,
            user_prompt TEXT DEFAULT '',
            agent_name TEXT,
            ai_response TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
    
    # Migrate existing table
    try:
        cursor.execute("ALTER TABLE captures ADD COLUMN user_prompt TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    
    # 4. Check if we have at least one conversation, if not create default
    cursor.execute("SELECT COUNT(*) FROM conversations")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO conversations (title) VALUES ('新对话')")
        
    conn.commit()
    conn.close()
    print(f"[Database] SQLite DB initialized at {DB_PATH}")

def add_conversation(title="新对话"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
    conv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return conv_id

def get_conversations():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, created_at FROM conversations ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "title": row[1],
            "created_at": row[2]
        }
        for row in rows
    ]

def update_conversation_title(conv_id, new_title):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE conversations SET title = ? WHERE id = ?", (new_title, conv_id))
    conn.commit()
    conn.close()

def delete_conversation(conv_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all image filenames in this conversation to delete from disk
    cursor.execute("SELECT image_filename FROM captures WHERE conversation_id = ?", (conv_id,))
    filenames = [row[0] for row in cursor.fetchall()]
    
    # Enable foreign keys to cascade delete captures automatically
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    
    conn.commit()
    conn.close()
    return filenames

def add_capture(conversation_id, image_filename, agent_name=None, user_prompt=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO captures (conversation_id, image_filename, user_prompt, agent_name, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (conversation_id, image_filename, user_prompt, agent_name))
    capture_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return capture_id

def update_ai_response(capture_id, ai_response, status='processing'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE captures
        SET ai_response = ?, status = ?
        WHERE id = ?
    """, (ai_response, status, capture_id))
    conn.commit()
    conn.close()


def reset_capture_analysis(capture_id, agent_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE captures
        SET agent_name = ?, ai_response = '', status = 'pending'
        WHERE id = ?
        """,
        (agent_name, capture_id),
    )
    conn.commit()
    changed = cursor.rowcount
    conn.close()
    return changed > 0

def get_capture(capture_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, conversation_id, timestamp, image_filename, agent_name, ai_response, status, user_prompt
        FROM captures
        WHERE id = ?
    """, (capture_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "conversation_id": row[1],
            "timestamp": row[2],
            "image_filename": row[3],
            "agent_name": row[4],
            "ai_response": row[5],
            "status": row[6],
            "user_prompt": row[7]
        }
    return None

def get_captures_by_conversation(conv_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, conversation_id, timestamp, image_filename, agent_name, ai_response, status, user_prompt
        FROM captures
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conv_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "conversation_id": row[1],
            "timestamp": row[2],
            "image_filename": row[3],
            "agent_name": row[4],
            "ai_response": row[5],
            "status": row[6],
            "user_prompt": row[7]
        }
        for row in rows
    ]

def get_all_captures():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, conversation_id, timestamp, image_filename, agent_name, ai_response, status, user_prompt
        FROM captures
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "conversation_id": row[1],
            "timestamp": row[2],
            "image_filename": row[3],
            "agent_name": row[4],
            "ai_response": row[5],
            "status": row[6],
            "user_prompt": row[7]
        }
        for row in rows
    ]

def delete_capture(capture_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT image_filename FROM captures WHERE id = ?", (capture_id,))
    row = cursor.fetchone()
    if row:
        filename = row[0]
        cursor.execute("DELETE FROM captures WHERE id = ?", (capture_id,))
        conn.commit()
        conn.close()
        return filename
    conn.close()
    return None

def clear_all_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT image_filename FROM captures")
    filenames = [row[0] for row in cursor.fetchall()]
    
    # Clean up both tables
    cursor.execute("DELETE FROM captures")
    cursor.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()
    return filenames
