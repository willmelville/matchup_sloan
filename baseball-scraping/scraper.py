from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import unidecode
import re
from event_handlers import remove_middle_initials
import json
import time
import datetime
from pathlib import Path
import pandas as pd
from typing import Optional
from dataclasses import dataclass, asdict
import logging
from tqdm import tqdm


def timeit(method):
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        logging.info(f'{method.__name__} took {te - ts:.2f} seconds')
        return result

    return timed

@timeit
def setup_webdriver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Disable images and other media for faster loading
    chrome_options.add_experimental_option(
        "prefs",
        {"profile.managed_default_content_settings.images": 2}
    )

    service = Service("/usr/local/bin/chromedriver")
    return webdriver.Chrome(service=service, options=chrome_options)


def get_element_safely(driver, by, selector, timeout=10):
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return element
    except TimeoutException:
        return None


@timeit
def get_lineup_subs_and_mapping(driver, team_class):
    lineup = []
    sub_ins = []
    player_id_map = {}
    position_map = {}
    try:
        ts = time.time()
        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f".{team_class} .batters tbody"))
        )
        te = time.time()
        logging.info(f'  Waiting for table took {te - ts:.2f} seconds')

        ts = time.time()
        rows = table.find_elements(By.TAG_NAME, "tr")[:-1]
        te = time.time()
        logging.info(f'  Finding table rows took {te - ts:.2f} seconds')

        ts = time.time()
        for row in rows:
            player_cell = row.find_element(By.CSS_SELECTOR, "td:first-child")
            player_link = player_cell.find_element(By.CSS_SELECTOR, "a[href^='https://www.mlb.com/player/']")
            player_id = int(player_link.get_attribute('href').split('/')[-1])
            player_name = unidecode.unidecode(player_link.get_attribute('aria-label'))

            player_id_map[player_id] = remove_middle_initials(player_name)
            is_sub = 'SubstitutePlayerWrapper' in player_cell.get_attribute('innerHTML')

            position = driver.execute_script("""
                var row = arguments[0];
                var positionSpan = row.querySelector('span[data-mlb-test="boxscoreTeamTablePlayerPosition"]');
                if (positionSpan) {
                    var fullPosition = positionSpan.textContent.trim();
                    return fullPosition.split('-')[0]; // Return only the first position
                }
                return '';
            """, row)

            position_map[player_id] = position if position else "Unknown"

            if is_sub:
                sub_ins.append(player_id)
            elif len(lineup) < 9:
                lineup.append(player_id)
        te = time.time()
        logging.info(f'  Processing rows took {te - ts:.2f} seconds')

    except Exception as e:
        logging.info(f"An error occurred while getting the lineup, substitutions, and player mapping: {e}")

    return lineup, sub_ins, player_id_map, position_map


@timeit
def get_bullpen_and_mapping(driver, team_class):
    bullpen = []
    pitcher_id_map = {}
    try:
        ts = time.time()
        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f".{team_class} .pitchers tbody"))
        )
        te = time.time()
        logging.info(f'  Waiting for table took {te - ts:.2f} seconds')

        ts = time.time()
        rows = table.find_elements(By.TAG_NAME, "tr")[:-1]  # Exclude the last row (totals)
        te = time.time()
        logging.info(f'  Finding table rows took {te - ts:.2f} seconds')

        ts = time.time()
        for row in rows:
            pitcher_cell = row.find_element(By.CSS_SELECTOR, "td:first-child")
            pitcher_link = pitcher_cell.find_element(By.CSS_SELECTOR, "a[href^='https://www.mlb.com/player/']")
            pitcher_id = int(pitcher_link.get_attribute('href').split('/')[-1])
            pitcher_name = unidecode.unidecode(pitcher_link.get_attribute('aria-label'))

            bullpen.append(pitcher_id)
            pitcher_id_map[pitcher_id] = pitcher_name
        te = time.time()
        logging.info(f'  Processing rows took {te - ts:.2f} seconds')

    except Exception as e:
        logging.info(f"An error occurred while getting the bullpen information: {e}")

    return bullpen, pitcher_id_map



@timeit
def process_box(driver, box_url):
    logging.info("processing box for: ", box_url)
    ts_total = time.time()

    ts = time.time()
    driver.set_page_load_timeout(2)
    try:
        driver.get(box_url)
    except TimeoutException:
        logging.info("Initial page load timed out, attempting to continue anyway")
    te = time.time()
    logging.info(f'  Loading box page took {te - ts:.2f} seconds')

    # Wait for a key element that indicates the page is interactive
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".away-r1"))
        )
    except TimeoutException:
        logging.info("Timed out waiting for key element, some data may be missing")

    results = {}
    for team in ['away', 'home']:
        ts = time.time()
        try:
            lineup, sub_ins, batter_map, position_map = get_lineup_subs_and_mapping(driver, f"{team}-r1")
            results[f'{team}_lineup'] = lineup
            results[f'{team}_sub_ins'] = sub_ins
            results[f'{team}_batter_map'] = batter_map
            results[f'{team}_position_map'] = position_map
        except Exception as e:
            logging.info(f"Error processing {team} lineup: {e}")
        te = time.time()
        logging.info(f'  Processing {team} team lineup took {te - ts:.2f} seconds')

        ts = time.time()
        try:
            bullpen, pitcher_map = get_bullpen_and_mapping(driver, f"{team}-r4")
            results[f'{team}_bullpen'] = bullpen
            results[f'{team}_pitcher_map'] = pitcher_map
        except Exception as e:
            logging.info(f"Error processing {team} bullpen: {e}")
        te = time.time()
        logging.info(f'  Processing {team} team bullpen took {te - ts:.2f} seconds')

        # Combine batter and pitcher maps
        results[f'{team}_player_map'] = {**results.get(f'{team}_batter_map', {}), **results.get(f'{team}_pitcher_map', {})}

    te_total = time.time()
    logging.info(f'  Total processing time: {te_total - ts_total:.2f} seconds')

    return (
        results.get('away_lineup', []), results.get('away_sub_ins', []), results.get('away_player_map', {}),
        results.get('away_bullpen', []), results.get('away_position_map', {}),
        results.get('home_lineup', []), results.get('home_sub_ins', []), results.get('home_player_map', {}),
        results.get('home_bullpen', []), results.get('home_position_map', {})
    )


@timeit
def process_summary(driver, summary_url, home_abbr, away_abbr):
    ts_total = time.time()

    # Set a short page load timeout and attempt to load the summary page
    ts = time.time()
    driver.set_page_load_timeout(2)
    try:
        driver.get(summary_url)
    except TimeoutException:
        logging.info("Initial page load timed out, attempting to continue anyway")
    te = time.time()
    logging.info(f'  Loading summary page took {te - ts:.2f} seconds')

    # Wait for a key element that indicates the page is interactive
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class, 'PlayFeedstyle__InningHeader')]")
            )
        )
    except TimeoutException:
        logging.info("Timed out waiting for key element, some data may be missing")

    game_summary = []
    current_inning = None

    ts = time.time()
    try:
        # Locate all relevant event elements
        events = driver.find_elements(
            By.XPATH,
            "//div[contains(@class, 'PlayFeedstyle__InningHeader') or "
            "contains(@class, 'SummaryPlaystyle__SummaryPlayWrapper')]"
        )
        te = time.time()
        logging.info(f'  Finding all events took {te - ts:.2f} seconds')

        ts = time.time()
        for event in events:
            classes = event.get_attribute('class')
            if 'PlayFeedstyle__InningHeader' in classes:
                # Extract and store inning information
                inning = event.text.strip()
                game_summary.append({"inning": inning, "events": []})
                current_inning = inning
            else:
                try:
                    # Extract all event details within this wrapper
                    sub_events = event.find_elements(
                        By.XPATH,
                        ".//div[contains(@class, 'SummaryPlayEventsstyle__SummaryPlayEventsWrapper')]"
                    )

                    for sub_event in sub_events:
                        event_types = sub_event.find_elements(
                            By.XPATH,
                            ".//div[contains(@class, 'PlayActionstyle__PlayActionEvent')]"
                        )
                        event_descriptions = sub_event.find_elements(
                            By.XPATH,
                            ".//div[contains(@class, 'PlayActionstyle__PlayActionDescription')]"
                        )
                        score_updates = sub_event.find_elements(
                            By.XPATH,
                            ".//div[contains(@class, 'PlayScoresstyle__TeamScoresWrapper')]"
                        )

                        for event_type, event_description in zip(event_types, event_descriptions):
                            event_type_text = event_type.text.strip()
                            event_description_text = event_description.text.strip()

                            # Extract the atbat index
                            atbat_index = event_type.get_attribute('data-atbat-index')
                            if atbat_index is None:
                                atbat_index = event_description.get_attribute('data-atbat-index')

                            if atbat_index is not None:
                                try:
                                    atbat_index = int(atbat_index) + 1  # 0 index -> 1 index
                                except ValueError:
                                    logging.info(f"      Invalid atbat-index value: {atbat_index}")
                                    atbat_index = None
                            else:
                                logging.info("      No atbat-index found for this event.")

                            # Process score updates
                            score_update = None
                            if score_updates:
                                try:
                                    score_update = {
                                        away_abbr: int(score_updates[0].text.split(',')[0].split()[-1]),
                                        home_abbr: int(score_updates[1].text.split()[-1])
                                    }
                                except (IndexError, ValueError) as e:
                                    logging.info(f"      Error parsing score updates: {e}")

                            # Process outs updates
                            outs_update = None
                            try:
                                outs_element = event_description.find_element(
                                    By.XPATH,
                                    ".//div[contains(@class, 'SummaryPlayEventsstyle__OutsWrapper')]"
                                )
                                if outs_element and outs_element.text.strip():
                                    try:
                                        outs_update = int(outs_element.text.strip().split()[0])
                                    except ValueError:
                                        logging.info(
                                            f"      Error parsing outs updates for event: {event_type_text} - {event_description_text}")
                            except Exception as e:
                                logging.info(f"      No outs element found or error: {e}")

                            # Handle offensive substitutions specifically
                            if "Offensive Substitution:" in event_description_text:
                                # Use regex to extract all 'Offensive Substitution: <desc>' parts
                                substitution_pattern = r'Offensive Substitution:\s*(.*?)\.?(?=\s*Offensive Substitution:|$)'
                                substitutions = re.findall(substitution_pattern, event_description_text, re.IGNORECASE | re.DOTALL)
                                logging.info(f"      Found {len(substitutions)} offensive substitution(s)")

                                for idx, sub_desc in enumerate(substitutions):
                                    sub_desc = sub_desc.strip()
                                    detailed_description = f"Offensive Substitution: {sub_desc}"
                                    logging.info(f"        Processing substitution {idx+1}: {detailed_description}")

                                    event_entry = {
                                        "type": "Offensive Substitution",
                                        "description": detailed_description,
                                        "score_update": score_update,
                                        "outs_update": outs_update,
                                        "atbat_index": atbat_index
                                    }

                                    # Append the event to the current inning's events
                                    if current_inning and game_summary:
                                        game_summary[-1]["events"].append(event_entry)
                                    else:
                                        logging.info(
                                            f"      Skipped event due to no current inning: Offensive Substitution - {sub_desc}")
                            elif "Defensive Substitution:" in event_description_text:
                                # Use regex to extract all 'Defensive Substitution: <desc>' parts
                                substitution_pattern = r'Defensive Substitution:\s*(.*?)\.?(?=\s*Defensive Substitution:|$)'
                                substitutions = re.findall(substitution_pattern, event_description_text, re.IGNORECASE | re.DOTALL)
                                logging.info(f"      Found {len(substitutions)} defensive substitution(s)")

                                for idx, sub_desc in enumerate(substitutions):
                                    sub_desc = sub_desc.strip()
                                    detailed_description = f"Defensive Substitution: {sub_desc}"
                                    logging.info(f"        Processing substitution {idx+1}: {detailed_description}")

                                    event_entry = {
                                        "type": "Defensive Sub",
                                        "description": detailed_description,
                                        "score_update": score_update,
                                        "outs_update": outs_update,
                                        "atbat_index": atbat_index
                                    }

                                    # Append the event to the current inning's events
                                    if current_inning and game_summary:
                                        game_summary[-1]["events"].append(event_entry)
                                    else:
                                        logging.info(
                                            f"      Skipped event due to no current inning: Defensive Substitution - {sub_desc}")

                            else:
                                event_entry = {
                                    "type": event_type_text,
                                    "description": event_description_text,
                                    "score_update": score_update,
                                    "outs_update": outs_update,
                                    "atbat_index": atbat_index
                                }

                                # Append the event to the current inning's events
                                if current_inning and game_summary:
                                    game_summary[-1]["events"].append(event_entry)
                                else:
                                    logging.info(
                                        f"      Skipped event due to no current inning: {event_type_text} - {event_description_text}")

                except Exception as e:
                    logging.info(f"    Error processing sub_event: {e}")
        te = time.time()
        logging.info(f'  Processing all events took {te - ts:.2f} seconds')
    except Exception as e:
        logging.info(f"Error finding or processing events: {e}")

    te_total = time.time()
    logging.info(f'  Total processing time: {te_total - ts_total:.2f} seconds')

    return game_summary


@dataclass
class GameData:
    """Container for scraped game data"""
    away_lineup: list
    away_sub_ins: list
    away_player_map: dict
    away_bullpen: list
    away_position_map: dict
    home_lineup: list
    home_sub_ins: list
    home_player_map: dict
    home_bullpen: list
    home_position_map: dict
    game_summary: list
    game_pk: str
    home_abbr: str
    away_abbr: str


class GameScraper:
    def __init__(self, games_csv: str, output_dir: str = "scraped_games"):
        self.games_df = pd.read_csv(games_csv)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Setup logging
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # File handler
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            handlers=[
                logging.FileHandler(f"logs/scraping_{timestamp}.log"),
                logging.StreamHandler()  # Also print to console
            ]
        )
        self.logger = logging

    def _is_game_data_complete(self, game_path: Path) -> bool:
        """Check if existing game data is complete (has non-empty lineups)."""
        try:
            with open(game_path, 'r') as f:
                game_data = json.load(f)
                return len(game_data.get('away_lineup', [])) > 0 and len(game_data.get('home_lineup', [])) > 0
        except (json.JSONDecodeError, FileNotFoundError):
            return False

    def scrape_games(self, start_index: int = 0, end_index: Optional[int] = None) -> None:
        """Scrape games and save data, checking for existing files and data completeness."""
        driver = setup_webdriver()
        try:
            games_to_process = self.games_df.iloc[start_index:end_index] if end_index else self.games_df.iloc[
                                                                                           start_index:]

            self.logger.info(f"Starting scraping of {len(games_to_process)} games")
            failed_games = []

            for idx, row in tqdm(games_to_process.iterrows(), total=len(games_to_process), desc="Scraping games"):
                game_pk = str(row['game_pk'])
                output_path = self.output_dir / f"game_{game_pk}.json"

                # Check if the game file already exists and has complete data
                if output_path.exists():
                    if self._is_game_data_complete(output_path):
                        self.logger.info(f"Game {game_pk} already scraped with complete data, skipping.")
                        continue
                    else:
                        self.logger.info(f"Game {game_pk} exists but has incomplete data, re-scraping.")

                try:
                    start_time = time.time()
                    game_data = self._scrape_single_game(driver, row)
                    self._save_game_data(game_data)

                    elapsed = time.time() - start_time
                    self.logger.info(f"Game {game_pk} scraped successfully in {elapsed:.2f} seconds")

                except Exception as e:
                    self.logger.error(f"Failed to scrape game {game_pk}: {str(e)}")
                    failed_games.append((game_pk, str(e)))

                # Small delay to avoid overwhelming the server
                time.sleep(1)

            if failed_games:
                self.logger.error(f"Failed to scrape {len(failed_games)} games:")
                for game_pk, error in failed_games:
                    self.logger.error(f"  Game {game_pk}: {error}")

        finally:
            driver.quit()

    def _scrape_single_game(self, driver, row) -> GameData:
        """Scrape data for a single game"""
        # Process box score
        box_data = process_box(driver, row['box_url'])
        away_lineup, away_sub_ins, away_player_map, away_bullpen, away_position_map, \
            home_lineup, home_sub_ins, home_player_map, home_bullpen, home_position_map = box_data

        # Process game summary
        game_summary = process_summary(driver, row['summary_url'], row['home_abbr'], row['away_abbr'])

        return GameData(
            away_lineup=away_lineup,
            away_sub_ins=away_sub_ins,
            away_player_map=away_player_map,
            away_bullpen=away_bullpen,
            away_position_map=away_position_map,
            home_lineup=home_lineup,
            home_sub_ins=home_sub_ins,
            home_player_map=home_player_map,
            home_bullpen=home_bullpen,
            home_position_map=home_position_map,
            game_summary=game_summary,
            game_pk=str(row['game_pk']),
            home_abbr=row['home_abbr'],
            away_abbr=row['away_abbr']
        )

    def _save_game_data(self, game_data: GameData) -> None:
        """Save game data to JSON file"""
        output_path = self.output_dir / f"game_{game_data.game_pk}.json"
        with open(output_path, 'w') as f:
            json.dump(asdict(game_data), f)


if __name__ == "__main__":
    # Example usage:
    # First, scrape all games
    scraper = GameScraper("urls/gameday_urls2023.csv")
    scraper.scrape_games(start_index=0)