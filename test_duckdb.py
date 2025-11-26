#!/usr/bin/env python3
"""
DuckDB Manager Test Suite

Tests the DuckDB integration for caching large datasets from Ace queries.
"""

import sys
import os
import pandas as pd
from datetime import datetime
import tempfile
import shutil

# Import the DuckDB manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duckdb_manager import DuckDBManager


def get_test_db_path():
    """Create a temporary directory for test database"""
    test_dir = tempfile.mkdtemp(prefix="duckdb_test_")
    return os.path.join(test_dir, "test_cache.duckdb")


def cleanup_test_db(db_path):
    """Clean up test database directory"""
    test_dir = os.path.dirname(db_path)
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


def test_initialization():
    """Test DuckDB manager initialization"""
    print("=== Test 1: Initialization ===")
    try:
        # Use a test database path instead of default
        test_db_path = get_test_db_path()
        manager = DuckDBManager(db_path=test_db_path, max_size_mb=100)

        assert manager.conn is not None, "Connection should be initialized"
        assert isinstance(manager.datasets, dict), "Datasets should be a dict"
        assert os.path.exists(test_db_path), "Database file should be created"
        print("✅ Initialization test passed")
        return manager, test_db_path
    except Exception as e:
        print(f"❌ Initialization test failed: {e}")
        raise


def test_store_dataframe(manager):
    """Test storing a DataFrame in DuckDB"""
    print("\n=== Test 2: Store DataFrame ===")
    try:
        # Create test DataFrame
        df = pd.DataFrame({
            'device_id': [1, 2, 3, 4, 5],
            'driver_name': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve'],
            'trips': [10, 20, 15, 30, 25],
            'distance_km': [100.5, 200.3, 150.2, 300.1, 250.4],
            'fuel_liters': [15.2, 28.4, 22.1, 42.3, 35.6]
        })

        # Store the DataFrame
        table_name = manager.store_dataframe(
            chat_id="test_chat_123",
            message_group_id="test_msg_456",
            df=df,
            question="Test question about trips",
            sql_query="SELECT * FROM trips WHERE date > '2024-01-01'"
        )

        # Verify storage
        assert table_name in manager.datasets, f"Table {table_name} should be in datasets"
        assert manager.datasets[table_name]['row_count'] == 5, "Should have 5 rows"
        assert manager.datasets[table_name]['column_count'] == 5, "Should have 5 columns"
        assert 'device_id' in manager.datasets[table_name]['columns'], "Should have device_id column"

        print(f"✅ Store DataFrame test passed - table: {table_name}")
        return table_name
    except Exception as e:
        print(f"❌ Store DataFrame test failed: {e}")
        raise


def test_basic_query(manager, table_name):
    """Test basic SQL query"""
    print("\n=== Test 3: Basic Query ===")
    try:
        # Query all data
        result_df, metadata = manager.query(f"SELECT * FROM {table_name}")

        assert len(result_df) == 5, "Should return 5 rows"
        assert metadata['row_count'] == 5, "Metadata should show 5 rows"
        assert metadata['column_count'] == 5, "Metadata should show 5 columns"
        assert 'device_id' in result_df.columns, "Result should have device_id column"

        print(f"✅ Basic query test passed - returned {len(result_df)} rows")
        return True
    except Exception as e:
        print(f"❌ Basic query test failed: {e}")
        raise


def test_filtered_query(manager, table_name):
    """Test filtered SQL query"""
    print("\n=== Test 4: Filtered Query ===")
    try:
        # Query with WHERE clause
        result_df, metadata = manager.query(
            f"SELECT * FROM {table_name} WHERE trips > 15"
        )

        assert len(result_df) == 3, "Should return 3 rows where trips > 15"
        assert all(result_df['trips'] > 15), "All returned rows should have trips > 15"

        print(f"✅ Filtered query test passed - returned {len(result_df)} rows")
        return True
    except Exception as e:
        print(f"❌ Filtered query test failed: {e}")
        raise


def test_aggregation_query(manager, table_name):
    """Test aggregation SQL query"""
    print("\n=== Test 5: Aggregation Query ===")
    try:
        # Query with aggregation
        result_df, metadata = manager.query(
            f"""
            SELECT
                COUNT(*) as total_drivers,
                SUM(trips) as total_trips,
                AVG(distance_km) as avg_distance,
                MAX(fuel_liters) as max_fuel
            FROM {table_name}
            """
        )

        assert len(result_df) == 1, "Aggregation should return 1 row"
        assert result_df['total_drivers'].iloc[0] == 5, "Should count 5 drivers"
        assert result_df['total_trips'].iloc[0] == 100, "Should sum to 100 trips"

        print(f"✅ Aggregation query test passed")
        print(f"   Total drivers: {result_df['total_drivers'].iloc[0]}")
        print(f"   Total trips: {result_df['total_trips'].iloc[0]}")
        print(f"   Avg distance: {result_df['avg_distance'].iloc[0]:.1f} km")
        return True
    except Exception as e:
        print(f"❌ Aggregation query test failed: {e}")
        raise


def test_groupby_query(manager, table_name):
    """Test GROUP BY SQL query"""
    print("\n=== Test 6: GROUP BY Query ===")
    try:
        # Query with GROUP BY
        result_df, metadata = manager.query(
            f"""
            SELECT
                device_id,
                SUM(trips) as total_trips,
                SUM(distance_km) as total_distance
            FROM {table_name}
            GROUP BY device_id
            ORDER BY total_trips DESC
            """
        )

        assert len(result_df) == 5, "Should return 5 rows (one per device)"
        assert result_df['total_trips'].iloc[0] == 30, "First row should be device with 30 trips"

        print(f"✅ GROUP BY query test passed")
        print(f"   Top device: {result_df['device_id'].iloc[0]} with {result_df['total_trips'].iloc[0]} trips")
        return True
    except Exception as e:
        print(f"❌ GROUP BY query test failed: {e}")
        raise


def test_limit_enforcement(manager, table_name):
    """Test that LIMIT is enforced for safety"""
    print("\n=== Test 7: Limit Enforcement ===")
    try:
        # Query without explicit LIMIT (should auto-add)
        result_df, metadata = manager.query(
            f"SELECT * FROM {table_name}",
            limit=3
        )

        assert len(result_df) == 3, "Should respect the limit parameter"
        assert 'LIMIT' in metadata['query_executed'].upper(), "Query should have LIMIT added"

        print(f"✅ Limit enforcement test passed - limited to {len(result_df)} rows")
        return True
    except Exception as e:
        print(f"❌ Limit enforcement test failed: {e}")
        raise


def test_get_dataset_info(manager, table_name):
    """Test getting dataset metadata"""
    print("\n=== Test 9: Get Dataset Info ===")
    try:
        info = manager.get_dataset_info(table_name)

        assert info is not None, "Should return dataset info"
        assert info['chat_id'] == "test_chat_123", "Should have correct chat_id"
        assert info['message_group_id'] == "test_msg_456", "Should have correct message_group_id"
        assert info['row_count'] == 5, "Should have correct row count"
        assert info['question'] == "Test question about trips", "Should have question"
        assert 'created_at' in info, "Should have creation timestamp"

        print(f"✅ Get dataset info test passed")
        print(f"   Chat ID: {info['chat_id']}")
        print(f"   Rows: {info['row_count']}")
        return True
    except Exception as e:
        print(f"❌ Get dataset info test failed: {e}")
        raise


def test_list_datasets(manager):
    """Test listing all datasets"""
    print("\n=== Test 10: List Datasets ===")
    try:
        datasets = manager.list_datasets()

        assert len(datasets) >= 1, "Should have at least 1 dataset"
        assert 'table_name' in datasets[0], "Dataset should have table_name"
        assert 'row_count' in datasets[0], "Dataset should have row_count"
        assert 'columns' in datasets[0], "Dataset should have columns"

        print(f"✅ List datasets test passed - found {len(datasets)} dataset(s)")
        for ds in datasets:
            print(f"   - {ds['table_name']}: {ds['row_count']} rows, {ds['column_count']} columns")
        return True
    except Exception as e:
        print(f"❌ List datasets test failed: {e}")
        raise


def test_multiple_datasets(manager):
    """Test storing and managing multiple datasets"""
    print("\n=== Test 12: Multiple Datasets ===")
    try:
        # Create second dataset
        df2 = pd.DataFrame({
            'vehicle_id': [10, 20, 30],
            'status': ['active', 'inactive', 'active'],
            'odometer': [50000, 75000, 60000]
        })

        table_name_2 = manager.store_dataframe(
            chat_id="test_chat_789",
            message_group_id="test_msg_012",
            df=df2,
            question="Second test question",
            sql_query="SELECT * FROM vehicles"
        )

        # Verify both tables exist
        datasets = manager.list_datasets()
        assert len(datasets) == 2, "Should have 2 datasets now"

        # Query second table
        result_df, metadata = manager.query(f"SELECT * FROM {table_name_2} WHERE status = 'active'")
        assert len(result_df) == 2, "Should return 2 active vehicles"

        print(f"✅ Multiple datasets test passed - managing {len(datasets)} datasets")
        return table_name_2
    except Exception as e:
        print(f"❌ Multiple datasets test failed: {e}")
        raise


def test_large_dataset():
    """Test with a large dataset (>1000 rows) to simulate real usage"""
    print("\n=== Test 13: Large Dataset ===")
    test_db_path = None
    try:
        test_db_path = get_test_db_path()
        manager = DuckDBManager(db_path=test_db_path, max_size_mb=100)

        # Create large DataFrame (simulating Ace returning 5000 rows)
        large_df = pd.DataFrame({
            'trip_id': range(5000),
            'device_id': [i % 100 for i in range(5000)],
            'distance': [10.5 + (i % 50) for i in range(5000)],
            'duration_min': [30 + (i % 120) for i in range(5000)],
            'fuel_used': [5.2 + (i % 20) * 0.5 for i in range(5000)]
        })

        table_name = manager.store_dataframe(
            chat_id="large_test",
            message_group_id="large_msg",
            df=large_df,
            question="Get all trips from last month",
            sql_query="SELECT * FROM trips WHERE date > '2024-01-01'"
        )

        # Test aggregation on large dataset
        result_df, metadata = manager.query(
            f"""
            SELECT
                device_id,
                COUNT(*) as trip_count,
                AVG(distance) as avg_distance,
                SUM(fuel_used) as total_fuel
            FROM {table_name}
            GROUP BY device_id
            ORDER BY trip_count DESC
            LIMIT 10
            """
        )

        assert len(result_df) == 10, "Should return top 10 devices"
        assert result_df['trip_count'].iloc[0] == 50, "Each device should have 50 trips"

        print(f"✅ Large dataset test passed - processed {len(large_df)} rows")
        print(f"   Aggregated to {len(result_df)} groups")
        return True
    except Exception as e:
        print(f"❌ Large dataset test failed: {e}")
        raise
    finally:
        if test_db_path:
            cleanup_test_db(test_db_path)


def test_error_handling(manager):
    """Test error handling for invalid queries"""
    print("\n=== Test 14: Error Handling ===")
    try:
        # Test nonexistent table
        try:
            result_df, _metadata = manager.query("SELECT * FROM nonexistent_table")
            print("❌ Should have raised an error for nonexistent table")
            return False
        except Exception:
            print("✅ Correctly raised error for nonexistent table")

        # Test invalid SQL
        try:
            result_df, _metadata = manager.query("INVALID SQL QUERY")
            print("❌ Should have raised an error for invalid SQL")
            return False
        except Exception:
            print("✅ Correctly raised error for invalid SQL")

        print("✅ Error handling test passed")
        return True
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        raise


def test_sql_injection_protection():
    """Test SQL injection protection"""
    print("\n=== Test 15: SQL Injection Protection ===")
    test_db_path = None
    try:
        test_db_path = get_test_db_path()
        manager = DuckDBManager(db_path=test_db_path, max_size_mb=100)

        # Create a benign dataset
        df = pd.DataFrame({'col1': [1, 2, 3], 'col2': ['a', 'b', 'c']})

        # Test 1: Malicious chat_id with SQL injection attempt
        print("Testing malicious chat_id with SQL injection...")
        malicious_chat_id = "test'; DROP TABLE users; --"
        table_name = manager.store_dataframe(
            chat_id=malicious_chat_id,
            message_group_id="safe_msg",
            df=df
        )
        # Should have sanitized the table name - check it's safe (no SQL special chars)
        assert "'" not in table_name, "Table name should not contain quotes"
        assert ";" not in table_name, "Table name should not contain semicolons"
        assert "--" not in table_name, "Table name should not contain comment markers"
        assert table_name.startswith("ace_"), "Table name should start with ace_"
        # Verify it matches the safe pattern
        assert manager.TABLE_NAME_PATTERN.match(table_name), "Table name should match safe pattern"
        print(f"✅ Malicious chat_id sanitized to: {table_name}")

        # Test 2: Attempt DROP query
        print("Testing DROP query prevention...")
        try:
            manager.query("DROP TABLE " + table_name)
            print("❌ Should have blocked DROP query")
            return False
        except ValueError as e:
            if "dangerous" in str(e).lower() or "only select" in str(e).lower():
                print(f"✅ DROP query blocked: {e}")
            else:
                raise

        # Test 3: Attempt DELETE query
        print("Testing DELETE query prevention...")
        try:
            manager.query(f"DELETE FROM {table_name}")
            print("❌ Should have blocked DELETE query")
            return False
        except ValueError as e:
            if "dangerous" in str(e).lower() or "only select" in str(e).lower():
                print(f"✅ DELETE query blocked: {e}")
            else:
                raise

        # Test 4: Attempt UPDATE query
        print("Testing UPDATE query prevention...")
        try:
            manager.query(f"UPDATE {table_name} SET col1 = 999")
            print("❌ Should have blocked UPDATE query")
            return False
        except ValueError as e:
            if "dangerous" in str(e).lower() or "only select" in str(e).lower():
                print(f"✅ UPDATE query blocked: {e}")
            else:
                raise

        # Test 5: Verify LIMIT bypass fix (should not match "UNLIMITED")
        print("Testing LIMIT bypass protection...")
        # This should add LIMIT because "UNLIMITED" is not the same as "LIMIT"
        result_df, metadata = manager.query(f"SELECT * FROM {table_name} WHERE col2 != 'UNLIMITED'")
        assert "LIMIT" in metadata['query_executed'].upper(), "Should have added LIMIT"
        print(f"✅ LIMIT correctly added even with 'UNLIMITED' in query")

        print("✅ SQL injection protection test passed")
        return True
    except Exception as e:
        print(f"❌ SQL injection protection test failed: {e}")
        raise
    finally:
        if test_db_path:
            cleanup_test_db(test_db_path)


def test_cte_queries():
    """Test Common Table Expression (CTE) support"""
    print("\n=== Test 16: CTE Query Support ===")
    test_db_path = None
    try:
        test_db_path = get_test_db_path()
        manager = DuckDBManager(db_path=test_db_path, max_size_mb=100)

        # Create test data
        df = pd.DataFrame({
            'product': ['A', 'B', 'C', 'A', 'B'],
            'sales': [100, 200, 150, 120, 180],
            'region': ['North', 'South', 'North', 'South', 'North']
        })

        table_name = manager.store_dataframe(
            chat_id="cte_test",
            message_group_id="msg_cte",
            df=df
        )

        # Test CTE query
        print("Testing CTE query...")
        cte_query = f"""
        WITH regional_sales AS (
            SELECT region, SUM(sales) as total_sales
            FROM {table_name}
            GROUP BY region
        )
        SELECT * FROM regional_sales ORDER BY total_sales DESC
        """

        result_df, metadata = manager.query(cte_query)
        assert len(result_df) == 2, "Should return 2 regions"
        assert result_df['region'].iloc[0] == 'North', "North should have highest sales"
        print(f"✅ CTE query executed successfully: {len(result_df)} rows")

        # Test nested CTE
        print("Testing nested CTE...")
        nested_cte = f"""
        WITH product_totals AS (
            SELECT product, SUM(sales) as total
            FROM {table_name}
            GROUP BY product
        ),
        ranked_products AS (
            SELECT product, total,
                   ROW_NUMBER() OVER (ORDER BY total DESC) as rank
            FROM product_totals
        )
        SELECT * FROM ranked_products WHERE rank <= 2
        """

        result_df, metadata = manager.query(nested_cte)
        assert len(result_df) <= 2, "Should return top 2 products"
        print(f"✅ Nested CTE query executed successfully")

        print("✅ CTE query support test passed")
        return True
    except Exception as e:
        print(f"❌ CTE query support test failed: {e}")
        raise
    finally:
        if test_db_path:
            cleanup_test_db(test_db_path)


def test_absolute_limit_enforcement():
    """Test that safety limit is always enforced"""
    print("\n=== Test 17: Absolute LIMIT Enforcement ===")
    test_db_path = None
    try:
        test_db_path = get_test_db_path()
        manager = DuckDBManager(db_path=test_db_path, max_size_mb=100)

        # Create test data with 100 rows
        df = pd.DataFrame({
            'id': range(100),
            'value': range(100, 200)
        })

        table_name = manager.store_dataframe(
            chat_id="limit_test",
            message_group_id="msg_limit",
            df=df
        )

        # Test 1: Query without LIMIT should respect safety limit
        print("Testing query without LIMIT...")
        result_df, metadata = manager.query(f"SELECT * FROM {table_name}", limit=10)
        assert len(result_df) == 10, f"Should enforce safety limit of 10, got {len(result_df)}"
        print(f"✅ Safety limit enforced: {len(result_df)} rows")

        # Test 2: Query with LIMIT higher than safety limit should be capped
        print("Testing LIMIT bypass prevention...")
        result_df, metadata = manager.query(
            f"SELECT * FROM {table_name} LIMIT 50",
            limit=10
        )
        assert len(result_df) == 10, f"Should cap to safety limit of 10, got {len(result_df)}"
        print(f"✅ User LIMIT (50) capped to safety limit (10): {len(result_df)} rows")

        # Test 3: Query with LIMIT lower than safety limit should use user's LIMIT
        print("Testing user LIMIT lower than safety limit...")
        result_df, metadata = manager.query(
            f"SELECT * FROM {table_name} LIMIT 5",
            limit=10
        )
        assert len(result_df) == 5, f"Should respect user LIMIT of 5, got {len(result_df)}"
        print(f"✅ User LIMIT (5) respected when lower than safety limit: {len(result_df)} rows")

        # Test 4: Verify metadata includes both queries
        assert 'original_query' in metadata, "Metadata should include original query"
        assert 'query_executed' in metadata, "Metadata should include executed query"
        print(f"✅ Metadata correctly tracks both original and enforced queries")

        print("✅ Absolute LIMIT enforcement test passed")
        return True
    except Exception as e:
        print(f"❌ Absolute LIMIT enforcement test failed: {e}")
        raise
    finally:
        if test_db_path:
            cleanup_test_db(test_db_path)


def run_all_tests():
    """Run all tests"""
    print("🚀 Starting DuckDB Manager Test Suite\n")

    tests_passed = 0
    tests_failed = 0
    test_db_path = None

    try:
        # Test 1: Initialization
        manager, test_db_path = test_initialization()
        tests_passed += 1

        # Test 2: Store DataFrame
        table_name = test_store_dataframe(manager)
        tests_passed += 1

        # Test 3: Basic Query
        test_basic_query(manager, table_name)
        tests_passed += 1

        # Test 4: Filtered Query
        test_filtered_query(manager, table_name)
        tests_passed += 1

        # Test 5: Aggregation Query
        test_aggregation_query(manager, table_name)
        tests_passed += 1

        # Test 6: GROUP BY Query
        test_groupby_query(manager, table_name)
        tests_passed += 1

        # Test 7: Limit Enforcement
        test_limit_enforcement(manager, table_name)
        tests_passed += 1

        # Test 8: Get Dataset Info
        test_get_dataset_info(manager, table_name)
        tests_passed += 1

        # Test 9: List Datasets
        test_list_datasets(manager)
        tests_passed += 1

        # Test 10: Multiple Datasets
        test_multiple_datasets(manager)
        tests_passed += 1

        # Test 11: Large Dataset
        test_large_dataset()
        tests_passed += 1

        # Test 12: Error Handling
        test_error_handling(manager)
        tests_passed += 1

        # Test 13: SQL Injection Protection
        test_sql_injection_protection()
        tests_passed += 1

        # Test 14: CTE Query Support
        test_cte_queries()
        tests_passed += 1

        # Test 15: Absolute LIMIT Enforcement
        test_absolute_limit_enforcement()
        tests_passed += 1

    except Exception as e:
        tests_failed += 1
        print(f"\n💥 Test suite stopped due to error: {e}")
    finally:
        # Clean up test database
        if test_db_path:
            print(f"\n🧹 Cleaning up test database at {test_db_path}")
            try:
                cleanup_test_db(test_db_path)
                print("✅ Test database cleaned up")
            except Exception as e:
                print(f"⚠️  Failed to clean up test database: {e}")

    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    print(f"✅ Tests Passed: {tests_passed}")
    print(f"❌ Tests Failed: {tests_failed}")
    print(f"📈 Success Rate: {(tests_passed/(tests_passed+tests_failed)*100):.1f}%")
    print("="*60)

    if tests_failed == 0:
        print("\n🎉 All tests passed!")
        return True
    else:
        print(f"\n⚠️  {tests_failed} test(s) failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
