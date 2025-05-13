# monitor_workers.py
import redis
import time
import json
import os
import sys
import argparse
from prettytable import PrettyTable
from datetime import datetime

# Parse command line arguments
parser = argparse.ArgumentParser(description='Monitor Redis Queue workers and audio processing')
parser.add_argument('--refresh', type=int, default=5, help='Refresh interval in seconds')
parser.add_argument('--device', type=str, help='Filter by specific device ID')
args = parser.parse_args()

# Redis connection
redis_conn = redis.Redis(host='localhost', port=6379, db=0)

def clear_screen():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_worker_status():
    """Get status of all workers"""
    workers = []
    
    # Find all worker info in Redis
    for key in redis_conn.keys("worker:info:*"):
        try:
            device_id = key.decode('utf-8').replace("worker:info:", "")
            info = redis_conn.get(key)
            
            if info:
                parts = info.decode('utf-8').split(":")
                if len(parts) >= 3:
                    pid = parts[0]
                    queue = parts[1]
                    start_time = float(parts[2])
                    
                    workers.append({
                        "device_id": device_id,
                        "pid": pid,
                        "queue": queue,
                        "start_time": start_time,
                        "uptime": time.time() - start_time
                    })
        except Exception as e:
            print(f"Error parsing worker info: {e}")
    
    return workers

def get_session_stats():
    """Get statistics for all active sessions"""
    sessions = []
    
    # Find all session info in Redis
    for key in redis_conn.keys("session:info:*"):
        try:
            session_id = key.decode('utf-8').replace("session:info:", "")
            info = redis_conn.get(key)
            
            if info:
                session_data = json.loads(info)
                device_id = session_data.get("device_id", "unknown")
                
                # If filtering by device ID, skip non-matching sessions
                if args.device and args.device != device_id:
                    continue
                
                # Get session stats
                stats_key = f"stats:{session_id}"
                stats = {}
                
                if redis_conn.exists(stats_key):
                    raw_stats = redis_conn.hgetall(stats_key)
                    
                    # Convert byte keys/values to strings/numbers
                    for k, v in raw_stats.items():
                        key = k.decode('utf-8') if isinstance(k, bytes) else k
                        try:
                            # Try to convert to number if possible
                            value = float(v) if isinstance(v, bytes) else v
                        except:
                            value = v.decode('utf-8') if isinstance(v, bytes) else v
                        
                        stats[key] = value
                
                # Get session state
                state_key = f"session:state:{session_id}"
                state = {"active": "Unknown"}
                
                if redis_conn.exists(state_key):
                    try:
                        state_data = json.loads(redis_conn.get(state_key))
                        state = state_data
                    except:
                        pass
                
                # Add session to list
                sessions.append({
                    "session_id": session_id,
                    "device_id": device_id,
                    "start_time": session_data.get("start_time", 0),
                    "active": state.get("active", False),
                    "chunks_processed": stats.get("chunks_processed", 0),
                    "buffers_processed": stats.get("buffers_processed", 0),
                    "last_activity": stats.get("last_activity", 0)
                })
        except Exception as e:
            print(f"Error parsing session info: {e}")
    
    return sessions

def format_time(timestamp):
    """Format timestamp as readable time"""
    if not timestamp:
        return "N/A"
    
    try:
        dt = datetime.fromtimestamp(float(timestamp))
        return dt.strftime("%H:%M:%S")
    except:
        return "Invalid"

def format_duration(seconds):
    """Format seconds as readable duration"""
    if not seconds:
        return "N/A"
    
    try:
        seconds = float(seconds)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        elif minutes > 0:
            return f"{int(minutes)}m {int(seconds)}s"
        else:
            return f"{int(seconds)}s"
    except:
        return "Invalid"

def display_dashboard():
    """Display monitoring dashboard"""
    clear_screen()
    print(f"=== Audio Worker Monitor === (Refreshing every {args.refresh} seconds)")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Display worker status
    workers = get_worker_status()
    
    if workers:
        print("=== Active Workers ===")
        table = PrettyTable()
        table.field_names = ["Device ID", "PID", "Queue", "Uptime"]
        
        for worker in workers:
            # If filtering by device ID, skip non-matching workers
            if args.device and args.device != worker["device_id"]:
                continue
                
            table.add_row([
                worker["device_id"],
                worker["pid"],
                worker["queue"],
                format_duration(worker["uptime"])
            ])
        
        print(table)
    else:
        print("No active workers found")
    
    print()
    
    # Display session stats
    sessions = get_session_stats()
    
    if sessions:
        print("=== Active Sessions ===")
        table = PrettyTable()
        table.field_names = ["Session ID", "Device ID", "Status", "Chunks", "Buffers", "Last Activity"]
        
        for session in sessions:
            status = "Active" if session["active"] else "Ended"
            table.add_row([
                session["session_id"],
                session["device_id"],
                status,
                int(session["chunks_processed"]),
                int(session["buffers_processed"]),
                format_time(session["last_activity"])
            ])
        
        print(table)
    else:
        print("No active sessions found")
    
    # If filtering by device, show detailed stats
    if args.device:
        print(f"\n=== Detailed Stats for Device: {args.device} ===")
        
        # Get queue stats
        queue_name = f"user_{args.device}"
        jobs_in_queue = 0
        
        try:
            jobs_in_queue = redis_conn.llen(f"rq:queue:{queue_name}")
        except:
            pass
        
        print(f"Jobs waiting in queue: {jobs_in_queue}")
        
        # Get buffer stats for all sessions of this device
        buffer_sizes = []
        
        for session in sessions:
            if session["device_id"] == args.device:
                buffer_key = f"buffer:{session['session_id']}"
                if redis_conn.exists(buffer_key):
                    buffer_size = redis_conn.strlen(buffer_key)
                    buffer_sizes.append({
                        "session_id": session["session_id"],
                        "size": buffer_size
                    })
        
        if buffer_sizes:
            print("\nCurrent Audio Buffers:")
            for buffer in buffer_sizes:
                print(f"  Session {buffer['session_id']}: {buffer['size']} bytes")

if __name__ == "__main__":
    try:
        while True:
            display_dashboard()
            time.sleep(args.refresh)
    except KeyboardInterrupt:
        print("\nMonitoring stopped")
        sys.exit(0)