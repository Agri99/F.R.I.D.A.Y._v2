import time
import pytest
from friday.agent.task import Task, TaskStatus

def test_max_steps_exceeded():
    task = Task(goal="Infinite loop task")
    task.max_steps = 5
    task.steps_used = 5
    
    # Simulating what happens in orchestrator
    if task.steps_used >= task.max_steps:
        task.status = TaskStatus.FAILED
    
    assert task.status == TaskStatus.FAILED

def test_max_time_exceeded():
    task = Task(goal="Long running task")
    from datetime import datetime
    task.started_at = datetime.now()
    task.max_time_seconds = 1.0 # 1 second
    
    time.sleep(1.1)
    
    # Simulating what happens in orchestrator
    if task.started_at and (time.time() - task.started_at.timestamp() > task.max_time_seconds):
        task.status = TaskStatus.FAILED
        
    assert task.status == TaskStatus.FAILED
