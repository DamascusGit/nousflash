import json
import time
from sqlalchemy.orm import Session
from db.db_setup import get_db
from engines.post_retriever import (
    retrieve_recent_posts,
    fetch_external_context,
    fetch_notification_context,
    format_post_list
)
from engines.short_term_mem import generate_short_term_memory
from engines.long_term_mem import (
    create_embedding,
    retrieve_relevant_memories,
    store_memory,
)
from engines.post_maker import generate_post, generate_llm_response
from engines.significance_scorer import score_significance
from engines.post_sender import send_post, send_post_API
from engines.wallet_send import transfer_eth, wallet_address_in_post, get_wallet_balance, transfer_erc20, get_erc20_balance
from engines.follow_user import follow_by_username, decide_to_follow_users
from models import Post, User, TweetPost
from twitter.account import Account
import re
import os
from random import random

# MAX_REPLY_RATE = 0.02  # 2% (1 in 50) maximum reply rate
MAX_REPLY_RATE = 1  # 100% for testing
def run_pipeline(
    db: Session,
    account: Account,
    auth,
    private_key_hex: str,
    eth_mainnet_rpc_url: str,
    llm_api_key: str,
    openrouter_api_key: str,
    openai_api_key: str,
):
    """
    Run the main pipeline for generating and posting content.

    Args:
        db (Session): Database session
        account (Account): Twitter/X API account instance
        private_key_hex (str): Ethereum wallet private key
        eth_mainnet_rpc_url (str): Ethereum RPC URL
        llm_api_key (str): API key for LLM service
        openrouter_api_key (str): API key for OpenRouter
        openai_api_key (str): API key for OpenAI
    """
    # Step 1: Retrieve recent posts
    recent_posts = retrieve_recent_posts(db)
    formatted_recent_posts = format_post_list(recent_posts)
    print(f"Recent posts: {formatted_recent_posts}")

    # Step 2: Fetch external context
    # reply_fetch_list = []
    # for e in recent_posts:
    #     reply_fetch_list.append((e["tweet_id"], e["content"]))
    notif_context_tuple = fetch_notification_context(account)
    notif_context_id = [context[1] for context in notif_context_tuple]

    # filter all of the notifications for ones that haven't been seen before
    existing_tweet_ids = {tweet.tweet_id for tweet in db.query(TweetPost.tweet_id).all()}
    filtered_notif_context_tuple = [context for context in notif_context_tuple if context[1] not in existing_tweet_ids]

    # add to database every tweet id you have seen
    for id in notif_context_id:
        new_tweet_post = TweetPost(tweet_id=id)
        db.add(new_tweet_post)
        db.commit()

    # print(notif_context_id)
    notif_context = [context[0] for context in filtered_notif_context_tuple]
    # print(f"fetched context tweet ids: {new_ids}\n")
    print("New Notifications:\n")
    for notif in notif_context_tuple:
        print(f"- {notif[0]}, tweet at https://x.com/user/status/{notif[1]}\n")
    external_context = notif_context

    if len(notif_context) > 0:
        # Step 2.5 check wallet addresses in posts
        balance_ether = get_wallet_balance(private_key_hex, eth_mainnet_rpc_url)
        balance_erc20 = get_erc20_balance(private_key_hex, eth_mainnet_rpc_url, erc20_address)
        print(f"Agent wallet balance is {balance_ether} ETH now.\n")
        
        if balance_ether > 0.3:
            tries = 0
            max_tries = 2
            while tries < max_tries:
                wallet_data = wallet_address_in_post(
                    notif_context, private_key_hex, eth_mainnet_rpc_url, llm_api_key
                )
                print(f"Wallet addresses and amounts chosen from Posts: {wallet_data}")
                try:
                    wallets = json.loads(wallet_data)
                    if len(wallets) > 0:
                        # Send ETH to the wallet addresses with specified amounts
                        for wallet in wallets:
                            address = wallet["address"]
                            amount = wallet["amount"]
                            transfer_eth(
                                private_key_hex, eth_mainnet_rpc_url, address, amount
                            )
                        break
                    else:
                        print("No wallet addresses or amounts to send ETH to.")
                        break
                except json.JSONDecodeError as e:
                    print(f"Error parsing wallet data: {e}")
                    tries += 1
                    continue
                except KeyError as e:
                    print(f"Missing key in wallet data: {e}")
                    break
        
        time.sleep(5)

        if balance_erc20 > 0:
            tries = 0
            max_tries = 2
            while tries < max_tries:
                wallet_data = erc20_instructions_in_post(
                    notif_context, private_key_hex, eth_mainnet_rpc_url, llm_api_key
                )
                print(f"ERC20 address and amount chosen from Posts: {wallet_data}")
                try:
                    wallets = json.loads(wallet_data)
                    if len(wallets) > 0:
                        # Send ETH to the wallet addresses with specified amounts
                        for wallet in wallets:
                            address = wallet["address"]
                            erc20_address = wallet['erc20_address']
                            amount = wallet["amount"]
                            transfer_erc20(
                                private_key_hex, eth_mainnet_rpc_url, address, erc20_address, amount
                            )
                        break
                    else:
                        print("No wallet addresses and/or ERC20 address and/or amounts.")
                        break
                except json.JSONDecodeError as e:
                    print(f"Error parsing wallet data: {e}")
                    tries += 1
                    continue
                except KeyError as e:
                    print(f"Missing key in wallet data: {e}")
                    break
        
        time.sleep(5)

        print("Deciding following now")
        # Step 2.75 decide if follow some users
        # Handle replies to mentions and interactions
        handle_replies(db, account, auth, external_context, llm_api_key)

    # Step 2.5 check wallet addresses in posts
    balance_ether = get_wallet_balance(private_key_hex, eth_mainnet_rpc_url)
    print(f"Agent wallet balance is {balance_ether} ETH now.\n")
    
    if balance_ether > 0.3:
        tries = 0
        max_tries = 2
        while tries < max_tries:
            wallet_data = wallet_address_in_post(
                notif_context, private_key_hex, eth_mainnet_rpc_url, llm_api_key
            )
            print(f"Wallet addresses and amounts chosen from Posts: {wallet_data}")
            try:
                wallets = json.loads(wallet_data)
                if len(wallets) > 0:
                    # Send ETH to the wallet addresses with specified amounts
                    for wallet in wallets:
                        address = wallet["address"]
                        amount = wallet["amount"]
                        transfer_eth(
                            private_key_hex, eth_mainnet_rpc_url, address, amount
                        )
                    break
                else:
                    print("No wallet addresses or amounts to send ETH to.")
                    break
            except json.JSONDecodeError as e:
                print(f"Error parsing wallet data: {e}")
                tries += 1
                continue
            except KeyError as e:
                print(f"Missing key in wallet data: {e}")
                break
    
    time.sleep(5)

    print("Deciding following now")
    # Step 2.75 decide if follow some users
    tries = 0
    max_tries = 2
    while tries < max_tries:
        decision_data = decide_to_follow_users(db, notif_context, openrouter_api_key)
        print(f"Decisions from Posts: {decision_data}")
        try:
            decisions = json.loads(decision_data)
            if len(decisions) > 0:
                # Follow the users with specified scores
                for decision in decisions:
                    username = decision["username"]
                    score = decision["score"]
                    if score > 0.98:
                        follow_by_username(account, username)
                        print(
                            f"user {username} has a high rizz of {score}, now following."
                        )
                    else:
                        print(
                            f"Score {score} for user {username} is below or equal to 0.98. Not following."
                        )
                break
            else:
                print("No users to follow.")
                break
        except json.JSONDecodeError as e:
            print(f"Error parsing decision data: {e}")
            tries += 1
            continue
        except KeyError as e:
            print(f"Missing key in decision data: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            break
    
    time.sleep(5)

    # Step 3: Generate short-term memory
    short_term_memory = generate_short_term_memory(
        recent_posts, external_context, llm_api_key
    )
    print(f"Short-term memory: {short_term_memory}")

    # Step 4: Create embedding for short-term memory
    short_term_embedding = create_embedding(short_term_memory, openai_api_key)

    # Step 5: Retrieve relevant long-term memories
    long_term_memories = retrieve_relevant_memories(db, short_term_embedding)
    print(f"Long-term memories: {long_term_memories}")

    # Step 6: Generate new post
    new_post_content = generate_post(short_term_memory, long_term_memories, formatted_recent_posts, external_context, llm_api_key)
    new_post_content = new_post_content.strip('"')
    print(f"New post content: {new_post_content}")

    # Step 7: Score the significance of the new post
    significance_score = score_significance(new_post_content, llm_api_key)
    print(f"Significance score: {significance_score}")

    # Step 8: Store the new post in long-term memory if significant enough
    if significance_score >= 7:
        new_post_embedding = create_embedding(new_post_content, openai_api_key)
        store_memory(db, new_post_content, new_post_embedding, significance_score)

    # Step 9: Save the new post to the database
    ai_user = db.query(User).filter(User.username == "tee_hee_he").first()
    if not ai_user:
        ai_user = User(username="tee_hee_he", email="tee_hee_he@example.com")
        db.add(ai_user)
        db.commit()

    # THIS IS WHERE YOU WOULD INCLUDE THE POST_SENDER.PY FUNCTION TO SEND THE NEW POST TO TWITTER ETC
    if significance_score >= 3: # Only Bangers! lol
        res = send_post_API(auth, new_post_content)
        print(f"Posted API with tweet_id: {res}")

        if res is not None:
            print(f"Posted with tweet_id: {res}")
            new_db_post = Post(
                content=new_post_content,
                user_id=ai_user.id,
                username=ai_user.username,
                type="text",
                tweet_id=res,
            )
            db.add(new_db_post)
            db.commit()
        else:
            res = send_post(account, new_post_content)
            rest_id = (res.get('data', {})
                        .get('create_tweet', {})
                        .get('tweet_results', {})
                        .get('result', {})
                        .get('rest_id'))

            if rest_id is not None:
                print(f"Posted with tweet_id: {rest_id}")
                new_db_post = Post(
                    content=new_post_content,
                    user_id=ai_user.id,
                    username=ai_user.username,
                    type="text",
                    tweet_id=rest_id,
                )
                db.add(new_db_post)
                db.commit()

    print(
        f"New post generated with significance score {significance_score}: {new_post_content}"
    )


def handle_replies(db: Session, account: Account, auth, external_context, llm_api_key: str):
    """Handle replies to mentions and other interactions."""
    for context in external_context:
        # Extract user ID and content from the context
        # This assumes the context format from your post_retriever.py
        if isinstance(context, tuple) and len(context) == 2:
            content, tweet_id = context
            
            # Extract user ID from the content
            # This regex looks for @username pattern
            user_match = re.search(r'@(\w+)', content)
            if user_match:
                user_id = user_match.group(1)
                
                # Check if we should reply
                if should_reply(content, user_id, llm_api_key):
                    # Generate reply using the same prompt as regular tweets
                    reply_content = generate_post(
                        short_term_memory="",  # You might want to customize this
                        long_term_memories=[],  # And this
                        recent_posts=[],        # And this
                        external_context=content,
                        llm_api_key=llm_api_key
                    )
                    
                    # Send the reply
                    try:
                        response = account.reply(reply_content, tweet_id=tweet_id)
                        print(f"Replied to {user_id} with: {reply_content}")
                        
                        # Store the reply in the database
                        new_reply = Post(
                            content=reply_content,
                            user_id=1,  # Assuming this is your bot's user ID
                            username="tee_hee_he",
                            type="reply",
                            tweet_id=response.get('data', {}).get('id', None)
                        )
                        db.add(new_reply)
                        db.commit()
                        
                    except Exception as e:
                        print(f"Error sending reply: {e}")


def should_reply(content: str, user_id: str, llm_api_key: str) -> bool:
    """Use LLM to determine if we should reply based on content."""
    # Skip replies to self to avoid loops
    if user_id.lower() == "tee_hee_he":
        return False
    
    # Rate limiting check
    if random() > MAX_REPLY_RATE:
        return False
        
    # Use environment variable for reply prompt
    reply_prompt = os.getenv('REPLY_FILTER_PROMPT_TEMPLATE', '')
    if not reply_prompt:
        return False
        
    # Ask LLM if we should reply
    response = generate_llm_response(
        prompt=reply_prompt,
        content=content,
        llm_api_key=llm_api_key
    )
    
    return response.strip().lower() == 'true'