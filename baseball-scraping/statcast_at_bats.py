import csv
from io import StringIO
import pandas as pd


def get_at_bat_summary_for_game(input_csv, game_id):
    # Create a CSV reader from the input string
    f = StringIO(input_csv)
    reader = csv.DictReader(f)

    # Prepare an output string buffer
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames)

    # Write the header to the new CSV
    writer.writeheader()

    # Set to track the unique at-bat occurrences
    seen_at_bats = set()

    found = False
    # Iterate through each row in the input CSV
    for row in reader:
        # Only process rows for the specified game_id (game_pk)
        if row['game_pk'] == game_id:
            found = True
            # Create a unique key for each at-bat (game_pk, inning, inning_topbot, at_bat_number)
            at_bat_key = (row['game_pk'], row['inning'], row['inning_topbot'], row['at_bat_number'])

            # Write the row if it's the first occurrence of this at-bat
            if at_bat_key not in seen_at_bats:
                seen_at_bats.add(at_bat_key)
                writer.writerow(row)

    if not found:
        raise Exception(f"No game found for game id {game_id}")


    # Get the modified CSV as a string
    modified_csv = output.getvalue()

    # Convert the modified CSV string to a pandas DataFrame
    return pd.read_csv(StringIO(modified_csv))

