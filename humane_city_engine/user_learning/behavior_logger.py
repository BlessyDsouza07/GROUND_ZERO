def log_event(user_id, place_id, action):
    with open("logs/behavior.log", "a") as f:
        f.write(f"{user_id},{place_id},{action}\n")
