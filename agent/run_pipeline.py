import os
import time
import random
from datetime import datetime, timedelta
from db.db_setup import create_database, get_db
from db.db_seed import seed_database
from pipeline import run_pipeline
from dotenv import load_dotenv
import secrets
import hashlib
from eth_keys import keys
from requests_oauthlib import OAuth1
from tweepy import Client, Paginator, TweepyException
from engines.post_sender import send_post
from twitter.account import Account
import json


def generate_eth_account():
    # Securely generate a random number to use as a seed
    random_seed = secrets.token_bytes(32)

    hasher = hashlib.sha256()
    hasher.update(random_seed)
    hashed_output = hasher.digest()

    # Generate private key using the hash as a seed
    private_key = keys.PrivateKey(hashed_output)

    # Correct way to get the hex representation of the private key
    private_key_hex = private_key.to_hex()

    # Derive the public key
    public_key = private_key.public_key

    # Derive the Ethereum address
    eth_address = public_key.to_checksum_address()

    return private_key_hex, eth_address


def get_random_activation_time():
    """Returns a random time within the next 30 minutes"""
    return datetime.now() + timedelta(minutes=random.uniform(0, 30))


def get_random_duration():
    """Returns a random duration between 15-20 minutes"""
    return timedelta(minutes=random.uniform(15, 20))


def get_next_run_time():
    """Returns a random time between 30 seconds and 3 minutes from now"""
    return datetime.now() + timedelta(seconds=random.uniform(30, 180))


def main():
    load_dotenv()

    # Check if the database file exists
    if not os.path.exists("./data/agents.db"):
        print("Creating database...")
        create_database()
        print("Seeding database...")
        seed_database()
    else:
        print("Database already exists. Skipping creation and seeding.")

    db = next(get_db())

    # Load environment variables
    api_keys = {
        "llm_api_key": os.getenv("HYPERBOLIC_API_KEY"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY"),
        # 'news_api_key': os.getenv("NEWS_API_KEY")
    }

    # Accessing environment variables
    user_id = os.environ.get("USER_ID")
    user_name = os.environ.get("USER_NAME")
    eth_mainnet_rpc_url = os.environ.get("ETH_MAINNET_RPC_URL")
    email = os.environ.get("X_EMAIL")
    password = os.environ.get("X_PASSWORD")
    username = os.environ.get("X_USERNAME")
    auth_tokens = json.loads(os.environ.get("X_AUTH_TOKENS"))
    account = Account(ccokies=auth_tokens)

    private_key_hex, eth_address = generate_eth_account()
    print(f"generated agent exclusively-owned wallet: {eth_address}")
    # TODO: Agent need to know what's its wallet
    send_post(account, eth_address)

    # Do initial run on start
    print("\nPerforming initial pipeline run...")
    try:
        run_pipeline(
            db,
            account,
            private_key_hex,
            eth_mainnet_rpc_url,
            **api_keys,
        )
        print("Initial run completed successfully.")
    except Exception as e:
        print(f"Error during initial run: {e}")

    print("Starting continuous pipeline process...")

    while True:
        try:
            # Calculate next activation time and duration
            activation_time = get_random_activation_time()
            active_duration = get_random_duration()
            deactivation_time = activation_time + active_duration

            print(f"\nNext cycle:")
            print(f"Activation time: {activation_time.strftime('%I:%M:%S %p')}")
            print(f"Deactivation time: {deactivation_time.strftime('%I:%M:%S %p')}")
            print(f"Duration: {active_duration.total_seconds() / 60:.1f} minutes")

            # Wait until activation time
            while datetime.now() < activation_time:
                time.sleep(60)  # Check every minute

            # Pipeline is now active
            print(f"\nPipeline activated at: {datetime.now().strftime('%H:%M:%S')}")

            # Schedule first run
            next_run = get_next_run_time()

            # Run pipeline at random intervals until deactivation time
            while datetime.now() < deactivation_time:
                if datetime.now() >= next_run:
                    print(f"Running pipeline at: {datetime.now().strftime('%H:%M:%S')}")
                    try:
                        run_pipeline(
                            db,
                            account,
                            private_key_hex,
                            eth_mainnet_rpc_url,
                            **api_keys,
                        )
                    except Exception as e:
                        print(f"Error running pipeline: {e}")

                    # Schedule next run
                    next_run = get_next_run_time()
                    print(
                        f"Next run scheduled for: {next_run.strftime('%H:%M:%S')} "
                        f"({(next_run - datetime.now()).total_seconds():.1f} seconds from now)"
                    )

                # Short sleep to prevent CPU spinning
                time.sleep(1)

            print(f"Pipeline deactivated at: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Error in pipeline: {e}")
            continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcess terminated by user")
