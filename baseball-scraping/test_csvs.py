import os
import pandas as pd

def check_pitcher_nulls(directory):
    # List to store files with nulls in Home_Pitcher or Away_Pitcher columns
    files_with_nulls = []
    csv_files_found = False

    # Verify the directory exists
    if not os.path.isdir(directory):
        print(f"The directory '{directory}' does not exist.")
        return

    # Iterate through each file in the directory
    for filename in os.listdir(directory):
        if filename.endswith('.csv'):
            csv_files_found = True
            file_path = os.path.join(directory, filename)
            try:
                # Load the CSV file
                df = pd.read_csv(file_path)

                # Check for nulls in Home_Pitcher or Away_Pitcher columns
                if df['Home_Pitcher'].isnull().any() or df['Away_Pitcher'].isnull().any():
                    files_with_nulls.append(filename)
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    # Report results
    if not csv_files_found:
        print("No CSV files found in the specified directory.")
    elif files_with_nulls:
        print("Files with null values in Home_Pitcher or Away_Pitcher columns:")
        for file in files_with_nulls:
            print(file)
    else:
        print("No files with null values in Home_Pitcher or Away_Pitcher columns found.")

# Example usage
directory_path = './games'
check_pitcher_nulls(directory_path)
