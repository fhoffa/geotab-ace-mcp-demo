#!/usr/bin/env python3
"""
Memory Manager Test Suite

Tests the persistent memory system for storing and recalling learnings.
"""

import sys
import os
import tempfile
import shutil

# Import the memory manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_manager import MemoryManager


def test_initialization():
    """Test memory manager initialization"""
    print("=== Test 1: Initialization ===")
    try:
        # Use temp directory for test database
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_memories.db")

        manager = MemoryManager(db_path=db_path)
        assert manager.conn is not None, "Connection should be initialized"
        assert os.path.exists(db_path), "Database file should be created"

        print("✅ Initialization test passed")

        # Clean up
        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Initialization test failed: {e}")
        raise


def test_remember_and_recall():
    """Test storing and retrieving memories"""
    print("\n=== Test 2: Remember and Recall ===")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memories.db")

    try:
        manager = MemoryManager(db_path=db_path)

        # Store a memory
        mem_id = manager.remember(
            content="Fuel queries require explicit date ranges",
            category="gotcha",
            tags=["fuel", "date-range"],
            account=None
        )

        assert mem_id is not None, "Should return memory ID"
        assert len(mem_id) == 8, "Memory ID should be 8 characters"

        # Recall by search
        results = manager.recall(search="fuel")
        assert len(results) == 1, "Should find 1 memory"
        assert results[0]["id"] == mem_id, "Should find the stored memory"
        assert results[0]["category"] == "gotcha", "Category should match"
        assert "fuel" in results[0]["tags"], "Tags should include 'fuel'"

        # Recall by category
        results = manager.recall(category="gotcha")
        assert len(results) == 1, "Should find 1 gotcha"

        # Recall with no matches
        results = manager.recall(search="nonexistent")
        assert len(results) == 0, "Should find no memories"

        print(f"✅ Remember and Recall test passed - memory ID: {mem_id}")

        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Remember and Recall test failed: {e}")
        shutil.rmtree(temp_dir)
        raise


def test_categories():
    """Test category validation"""
    print("\n=== Test 3: Category Validation ===")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memories.db")

    try:
        manager = MemoryManager(db_path=db_path)

        # Valid categories
        valid_categories = [
            'gotcha', 'pattern', 'schema',
            'account-info', 'error-resolution', 'performance'
        ]

        for cat in valid_categories:
            mem_id = manager.remember(
                content=f"Test memory for {cat}",
                category=cat
            )
            assert mem_id is not None, f"Should accept category: {cat}"

        # Invalid category
        try:
            manager.remember(
                content="Test",
                category="invalid-category"
            )
            assert False, "Should reject invalid category"
        except ValueError as e:
            assert "Invalid category" in str(e), "Should report invalid category"

        print("✅ Category validation test passed")

        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Category validation test failed: {e}")
        shutil.rmtree(temp_dir)
        raise


def test_account_filtering():
    """Test account-specific memory filtering"""
    print("\n=== Test 4: Account Filtering ===")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memories.db")

    try:
        manager = MemoryManager(db_path=db_path)

        # Store global memory
        global_id = manager.remember(
            content="Global gotcha applies to all",
            category="gotcha"
        )

        # Store account-specific memories
        fleet1_id = manager.remember(
            content="Fleet1 has 500 vehicles",
            category="account-info",
            account="fleet1"
        )

        fleet2_id = manager.remember(
            content="Fleet2 uses metric units",
            category="account-info",
            account="fleet2"
        )

        # Recall for fleet1 - should get global + fleet1
        results = manager.recall(account="fleet1")
        result_ids = [r["id"] for r in results]
        assert global_id in result_ids, "Should include global memory"
        assert fleet1_id in result_ids, "Should include fleet1 memory"
        assert fleet2_id not in result_ids, "Should not include fleet2 memory"

        # Recall all
        all_results = manager.recall()
        assert len(all_results) == 3, "Should have 3 total memories"

        print("✅ Account filtering test passed")

        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Account filtering test failed: {e}")
        shutil.rmtree(temp_dir)
        raise


def test_context_summary():
    """Test session context generation"""
    print("\n=== Test 5: Context Summary ===")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memories.db")

    try:
        manager = MemoryManager(db_path=db_path)

        # Add some memories
        manager.remember(
            content="Critical: Always specify timezone",
            category="gotcha"
        )
        manager.remember(
            content="Use 'daily averages' for trends",
            category="pattern"
        )
        manager.remember(
            content="Fleet1 is in EST",
            category="account-info",
            account="fleet1"
        )

        # Get context summary
        summary = manager.format_context_summary(account="fleet1")

        assert "Geotab Memory Context" in summary, "Should have header"
        assert "Critical Gotchas" in summary, "Should have gotchas section"
        assert "timezone" in summary, "Should include gotcha content"

        print("✅ Context summary test passed")

        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Context summary test failed: {e}")
        shutil.rmtree(temp_dir)
        raise


def test_update_and_forget():
    """Test updating and deleting memories"""
    print("\n=== Test 6: Update and Forget ===")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memories.db")

    try:
        manager = MemoryManager(db_path=db_path)

        # Store a memory
        mem_id = manager.remember(
            content="Original content",
            category="pattern"
        )

        # Update content
        success = manager.update_memory(mem_id, content="Updated content")
        assert success, "Update should succeed"

        # Verify update
        results = manager.recall(search="Updated")
        assert len(results) == 1, "Should find updated memory"
        assert results[0]["content"] == "Updated content", "Content should be updated"

        # Mark as verified
        success = manager.update_memory(mem_id, verified=True)
        assert success, "Verify should succeed"

        # Delete memory
        success = manager.forget(mem_id)
        assert success, "Forget should succeed"

        # Verify deletion
        results = manager.recall()
        assert len(results) == 0, "Should have no memories after deletion"

        # Try to forget non-existent
        success = manager.forget("nonexistent")
        assert not success, "Should return False for non-existent memory"

        print("✅ Update and Forget test passed")

        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Update and Forget test failed: {e}")
        shutil.rmtree(temp_dir)
        raise


def test_usage_tracking():
    """Test that usage count increments on recall"""
    print("\n=== Test 7: Usage Tracking ===")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memories.db")

    try:
        manager = MemoryManager(db_path=db_path)

        # Store a memory
        mem_id = manager.remember(
            content="Test usage tracking",
            category="pattern"
        )

        # Recall multiple times
        for i in range(3):
            manager.recall(search="tracking")

        # Check usage count
        memories = manager.list_memories()
        assert len(memories) == 1, "Should have 1 memory"
        assert memories[0]["usage_count"] == 3, f"Usage count should be 3, got {memories[0]['usage_count']}"

        print("✅ Usage tracking test passed")

        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Usage tracking test failed: {e}")
        shutil.rmtree(temp_dir)
        raise


def test_stats():
    """Test memory statistics"""
    print("\n=== Test 8: Statistics ===")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memories.db")

    try:
        manager = MemoryManager(db_path=db_path)

        # Add various memories
        manager.remember("Gotcha 1", "gotcha")
        manager.remember("Gotcha 2", "gotcha")
        manager.remember("Pattern 1", "pattern")
        manager.remember("Account info", "account-info", account="fleet1")

        stats = manager.get_stats()

        assert stats["total_memories"] == 4, "Should have 4 total memories"
        assert stats["by_category"]["gotcha"] == 2, "Should have 2 gotchas"
        assert stats["by_category"]["pattern"] == 1, "Should have 1 pattern"
        assert "fleet1" in stats["by_account"], "Should have fleet1 account"

        print("✅ Statistics test passed")

        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Statistics test failed: {e}")
        shutil.rmtree(temp_dir)
        raise


def test_empty_content_validation():
    """Test that empty content is rejected"""
    print("\n=== Test 9: Empty Content Validation ===")
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_memories.db")

    try:
        manager = MemoryManager(db_path=db_path)

        # Empty string
        try:
            manager.remember("", "gotcha")
            assert False, "Should reject empty content"
        except ValueError:
            pass

        # Whitespace only
        try:
            manager.remember("   ", "gotcha")
            assert False, "Should reject whitespace-only content"
        except ValueError:
            pass

        print("✅ Empty content validation test passed")

        manager.close()
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"❌ Empty content validation test failed: {e}")
        shutil.rmtree(temp_dir)
        raise


def run_all_tests():
    """Run all memory manager tests"""
    print("=" * 60)
    print("MEMORY MANAGER TEST SUITE")
    print("=" * 60)

    tests = [
        test_initialization,
        test_remember_and_recall,
        test_categories,
        test_account_filtering,
        test_context_summary,
        test_update_and_forget,
        test_usage_tracking,
        test_stats,
        test_empty_content_validation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"Test failed with error: {e}")

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
