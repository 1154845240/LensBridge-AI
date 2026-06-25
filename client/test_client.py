import time
import os
import threading
from pynput import mouse
import client

def simulate_long_press(x, y, duration):
    print(f"[Test] Simulating mouse press at ({x}, {y})")
    client.on_click(x, y, mouse.Button.left, True)
    time.sleep(duration)
    print(f"[Test] Simulating mouse release at ({x}, {y})")
    client.on_click(x, y, mouse.Button.left, False)

def run_tests():
    # Make sure local_captures is empty or track file count
    initial_files = set(os.listdir("local_captures") if os.path.exists("local_captures") else [])
    
    print("\n--- Test 1: Successful Dual Long Press ---")
    # Simulate first long press (3.2 seconds) at (100, 100)
    simulate_long_press(100, 100, 3.2)
    
    # Wait 2 seconds
    print("[Test] Waiting 2 seconds before second press...")
    time.sleep(2.0)
    
    # Simulate second long press (3.5 seconds) at (500, 500)
    simulate_long_press(500, 500, 3.5)
    
    time.sleep(1.0) # wait for capture to write
    current_files = set(os.listdir("local_captures") if os.path.exists("local_captures") else [])
    new_files = current_files - initial_files
    assert len(new_files) == 1, f"Expected 1 new capture, got {len(new_files)}"
    print(f"[Test] Test 1 Passed! New file: {new_files}")
    
    print("\n--- Test 2: Timeout Cancellation ---")
    # Simulate first long press (3.1 seconds)
    simulate_long_press(100, 100, 3.1)
    
    # Wait 16 seconds (more than 15s timeout)
    print("[Test] Waiting 16 seconds to trigger timeout...")
    time.sleep(16.0)
    
    # Verify coord_a is reset to None
    assert client.coord_a is None, "Expected coord_a to be reset to None after 15s"
    print("[Test] Test 2 Passed! Coordinate A was successfully reset after timeout.")

if __name__ == "__main__":
    # Ensure capture folder exists
    os.makedirs("local_captures", exist_ok=True)
    run_tests()
