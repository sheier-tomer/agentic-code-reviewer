from src.indexing.chunker import CodeChunker, DocChunker, ChunkMetadata
from pathlib import Path


def test_code_chunker_function_extraction():
    chunker = CodeChunker()
    
    code = '''
def hello_world(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"

async def async_func():
    pass
'''
    
    chunks = chunker.chunk_file(Path("test.py"), code)
    
    assert len(chunks) >= 2
    
    function_chunks = [c for c in chunks if c.chunk_type == "function"]
    assert len(function_chunks) >= 2
    
    hello_chunk = next(c for c in function_chunks if c.symbol_name == "hello_world")
    assert hello_chunk.docstring == "Say hello."
    assert "def hello_world" in hello_chunk.content


def test_code_chunker_class_extraction():
    chunker = CodeChunker()
    
    code = '''
class UserService:
    """Service for users."""
    
    def __init__(self, db):
        self.db = db
    
    def get_user(self, user_id: int):
        return self.db.query(User).get(user_id)
'''
    
    chunks = chunker.chunk_file(Path("service.py"), code)
    
    class_chunks = [c for c in chunks if c.chunk_type == "class"]
    assert len(class_chunks) >= 1
    
    us_class = next(c for c in class_chunks if c.symbol_name == "UserService")
    assert us_class.docstring == "Service for users."


def test_doc_chunker_markdown():
    chunker = DocChunker()
    
    doc = '''# Introduction

This is the introduction.

## Getting Started

Follow these steps.

## API Reference

Here's the API.
'''
    
    chunks = chunker.chunk_file(Path("README.md"), doc)
    
    assert len(chunks) >= 1
    assert all(c.language == "markdown" for c in chunks)


def test_chunk_metadata():
    chunk = ChunkMetadata(
        file_path="src/test.py",
        chunk_type="function",
        symbol_name="test_func",
        start_line=10,
        end_line=20,
        content="def test_func(): pass",
        language="python",
    )
    
    assert chunk.file_path == "src/test.py"
    assert chunk.chunk_type == "function"
    assert chunk.symbol_name == "test_func"
