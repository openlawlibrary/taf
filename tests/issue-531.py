import sys

def cli_update_repo():
    try:
        success = update_repo()   # Assume update_repo is defined elsewhere
        if not success:
            raise Exception("Repo update failed")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)  

    print("Repo updated successfully")
    sys.exit(0)  

