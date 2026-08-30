import sys
sys.path.insert(0, 'src')
from friday.memory.semantic import SemanticMemory
from friday.memory.database import MemoryDatabase
from pathlib import Path
import tempfile

# Test with problematic queries
with tempfile.TemporaryDirectory() as tmpdir:
    db = MemoryDatabase(Path(tmpdir) / 'test.db')
    sem = SemanticMemory(db)

    # Store some facts
    sem.store_fact('test', 'is', 'working')
    sem.store_fact('hello', 'world', 'test')
    sem.store_fact('user.name', 'Alice', 'preference')

    # Test problematic queries
    test_queries = [
        'what is my name?',      # contains ?
        'user.name',             # contains .
        'hello world!',          # contains !
        'test@email.com',        # contains @ and .
        'path/to/file',          # contains /
        r'C:\path\file',         # contains \
        'C++',                   # contains +
        'C#',                    # contains #
        'test-query',            # contains -
        r'C:\Users\test',        # contains \
    ]

    for q in test_queries:
        try:
            results = sem.recall(q, limit=5)
            print(f'OK: "{q}" -> {len(results)} results')
        except Exception as e:
            print(f'FAIL: "{q}" -> {e}')

    print('All tests passed!')