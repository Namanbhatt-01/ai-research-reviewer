import os
import sqlite3
import datetime
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

from src.utils.logger import logger


class StateManager:
    """
    Manages the state of the research pipeline using a local SQLite database.
    Provides resumability and provenance tracking.
    """
    def __init__(self, db_path: str = "data/state.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._initialize_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.commit()
            conn.close()

    def _initialize_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Workflows (Topics)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_name TEXT NOT NULL,
                    topic_slug TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tasks (Phases)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id INTEGER NOT NULL,
                    phase_name TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(id),
                    UNIQUE(workflow_id, phase_name)
                )
            ''')
            
            # Artifacts (Files)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    artifact_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                )
            ''')

    # --- Workflow Methods ---
    def get_or_create_workflow(self, topic_name: str, topic_slug: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflows WHERE topic_slug = ?", (topic_slug,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            cursor.execute(
                "INSERT INTO workflows (topic_name, topic_slug) VALUES (?, ?)",
                (topic_name, topic_slug)
            )
            workflow_id = cursor.lastrowid
            
            cursor.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
            return dict(cursor.fetchone())
            
    def update_workflow_status(self, workflow_id: int, status: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE workflows SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, workflow_id)
            )

    def get_all_workflows(self) -> List[Dict[str, Any]]:
        """Retrieves all workflows sorted by most recent first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflows ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_workflow_by_slug(self, topic_slug: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific workflow by its topic slug."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflows WHERE topic_slug = ?", (topic_slug,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def delete_workflow(self, topic_slug: str) -> bool:
        """Deletes a workflow and all its associated tasks by topic slug."""
        workflow = self.get_workflow_by_slug(topic_slug)
        if not workflow:
            return False
            
        workflow_id = workflow['id']
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM artifacts WHERE task_id IN (SELECT id FROM tasks WHERE workflow_id = ?)", (workflow_id,))
            cursor.execute("DELETE FROM tasks WHERE workflow_id = ?", (workflow_id,))
            cursor.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            return True

    # --- Task Methods ---
    def get_task(self, workflow_id: int, phase_name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tasks WHERE workflow_id = ? AND phase_name = ?",
                (workflow_id, phase_name)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_workflow_tasks(self, workflow_id: int) -> List[Dict[str, Any]]:
        """Retrieves all tasks for a specific workflow."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT phase_name, status, error_message FROM tasks WHERE workflow_id = ?", (workflow_id,))
            return [dict(row) for row in cursor.fetchall()]

    def create_or_start_task(self, workflow_id: int, phase_name: str) -> int:
        """Creates a task if it doesn't exist, and marks it as RUNNING."""
        task = self.get_task(workflow_id, phase_name)
        now = datetime.datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if task:
                cursor.execute(
                    "UPDATE tasks SET status = 'RUNNING', started_at = ?, error_message = NULL WHERE id = ?",
                    (now, task['id'])
                )
                return task['id']
            else:
                cursor.execute(
                    "INSERT INTO tasks (workflow_id, phase_name, status, started_at) VALUES (?, ?, 'RUNNING', ?)",
                    (workflow_id, phase_name, now)
                )
                return cursor.lastrowid

    def mark_task_complete(self, task_id: int):
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET status = 'COMPLETED', completed_at = ? WHERE id = ?",
                (now, task_id)
            )
            logger.info(f"Task {task_id} completed.")

    def mark_task_failed(self, task_id: int, error_message: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET status = 'FAILED', error_message = ? WHERE id = ?",
                (error_message, task_id)
            )
            logger.error(f"Task {task_id} failed: {error_message}")

    def reset_task(self, workflow_id: int, phase_name: str):
        """Forces a task back to PENDING, useful for --rerun commands."""
        task = self.get_task(workflow_id, phase_name)
        if task:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE tasks SET status = 'PENDING', started_at = NULL, completed_at = NULL, error_message = NULL WHERE id = ?",
                    (task['id'],)
                )
                logger.info(f"Task '{phase_name}' reset to PENDING.")

    # --- Artifact Methods ---
    def log_artifact(self, task_id: int, artifact_type: str, file_path: str):
        """Logs an artifact ensuring we track its existence."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if this exact file under this task already exists to bump version
            cursor.execute(
                "SELECT version FROM artifacts WHERE task_id = ? AND artifact_type = ? ORDER BY version DESC LIMIT 1",
                (task_id, artifact_type)
            )
            row = cursor.fetchone()
            version = (row['version'] + 1) if row else 1
            
            cursor.execute(
                "INSERT INTO artifacts (task_id, artifact_type, file_path, version) VALUES (?, ?, ?, ?)",
                (task_id, artifact_type, file_path, version)
            )
            logger.info(f"Logged artifact: {artifact_type} v{version} -> {file_path}")

    def get_artifacts(self, task_id: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM artifacts WHERE task_id = ?", (task_id,))
            return [dict(row) for row in cursor.fetchall()]
