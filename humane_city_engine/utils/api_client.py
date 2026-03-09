import requests
import time
from utils.logger import get_logger

logger = get_logger("APIClient")


def safe_api_request(url, retries=3, timeout=10):
    """
    Safely fetch data from API with retry logic.
    """

    for attempt in range(retries):

        try:

            logger.info(f"API request attempt {attempt+1}: {url}")

            response = requests.get(url, timeout=timeout)

            if response.status_code == 200:

                logger.info("API request successful")

                return response.json()

            elif response.status_code == 429:

                logger.warning("API rate limit reached")

                time.sleep(3)

            else:

                logger.warning(f"API returned status {response.status_code}")

        except requests.exceptions.Timeout:

            logger.error("API timeout")

        except requests.exceptions.ConnectionError:

            logger.error("Connection error")

        except requests.exceptions.RequestException as e:

            logger.error(f"Request exception: {e}")

        except Exception as e:

            logger.error(f"Unexpected API error: {e}")

        time.sleep(2)

    logger.error("API failed after retries")

    return None