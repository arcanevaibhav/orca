import os


def add_user():
    try:
        # Read existing user IDs
        if os.path.exists("user_id.txt"):
            with open("user_id.txt", "r") as user_file:
                user_ids = user_file.read().splitlines()
        else:
            user_ids = []

        # Prompt for new user ID
        new_user_id = input("Enter the new User ID: ").strip()
        if not new_user_id:
            print("No User ID entered. Exiting...")
            return

        # Add new user ID to the list
        user_ids.append(new_user_id)
        with open("user_id.txt", "w") as user_file:
            user_file.write("\n".join(user_ids))

        # Create corresponding empty proxy file
        proxy_file_name = f"proxy{len(user_ids)}.txt"
        with open(proxy_file_name, "w") as proxy_file:
            pass  # Create an empty file

        print(f"User ID '{new_user_id}' added successfully.")
        print(f"Created an empty proxy file: {proxy_file_name}")
        print("Please add proxies to the file manually and restart the script.")
        print("Exiting...")

    except Exception as e:
        print(f"An error occurred: {e}")


def start_script():
    print("Starting the main script...")
    # Call your main script logic here (e.g., starting WebSocket connections)
    pass


def main_menu():
    print("Main Menu:")
    print("1. Add a new user ID and create proxy file")
    print("2. Start the script with existing configurations")
    option = input("Select an option (1/2): ").strip()

    if option == "1":
        add_user()
    elif option == "2":
        start_script()
    else:
        print("Invalid option. Exiting...")


if __name__ == "__main__":
    main_menu()
