import json
from sqlalchemy.orm import Session
from db.db_setup import get_db
from engines.post_retriever import retrieve_recent_posts, fetch_external_context, fetch_notification_context
from engines.short_term_mem import generate_short_term_memory
from engines.long_term_mem import create_embedding, retrieve_relevant_memories, store_memory
from engines.post_maker import generate_post
from engines.significance_scorer import score_significance
from engines.post_sender import send_post
from engines.wallet_send import transfer_eth, wallet_address_in_post, get_wallet_balance
from engines.follow_user import follow_by_username, decide_to_follow_users
from models import Post, User

def run_pipeline(db: Session, user_id, user_name, auth, client, private_key_hex: str, eth_mainnet_rpc_url: str, llm_api_key: str, openrouter_api_key: str, openai_api_key: str):
    """
    Run the main pipeline for generating and posting content.
    
    Args:
        db (Session): Database session
        openrouter_api_key (str): API key for OpenRouter
        openai_api_key (str): API key for OpenAI
        your_site_url (str): Your site URL for OpenRouter API
        your_app_name (str): Your app name for OpenRouter API
        news_api_key (str): API key for news service
    """
    # Step 1: Retrieve recent posts
    recent_posts = retrieve_recent_posts(db)
    print(f"Recent posts: {recent_posts}")
    
    # Step 2: Fetch external context
    # LEAVING THIS EMPTY FOR ANYTHING YOU WANT TO SUBSTITUTE (NEWS API, DATA SOURCE ETC)
    reply_fetch_list = []
    for e in recent_posts:
        reply_fetch_list.append((e["tweet_id"], e["content"]))
    notif_context = fetch_notification_context(user_id, user_name, auth, client, reply_fetch_list)
    print(f"Notifications: {notif_context}")
    external_context = notif_context


    if len(notif_context) > 0:
        # Step 2.5 check wallet addresses in posts
        if get_wallet_balance(private_key_hex, eth_mainnet_rpc_url) > 0.3:
            tries = 0
            max_tries = 2
            while tries < max_tries:
                wallet_data = wallet_address_in_post(notif_context, private_key_hex, eth_mainnet_rpc_url, llm_api_key)
                print(f"Wallet addresses and amounts chosen from Posts: {wallet_data}")
                try:
                    wallets = json.loads(wallet_data)
                    if len(wallets) > 0:
                        # Send ETH to the wallet addresses with specified amounts
                        for wallet in wallets:
                            address = wallet['address']
                            amount = wallet['amount']
                            transfer_eth(private_key_hex, eth_mainnet_rpc_url, address, amount)
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

        # Step 2.75 decide if follow some users
        tries = 0
        max_tries = 2
        while tries < max_tries:
            decision_data = decide_to_follow_users(notif_context, openrouter_api_key)
            print(f"Decisions from Posts: {decision_data}")
            try:
                decisions = json.loads(decision_data)
                if len(decisions) > 0:
                    # Follow the users with specified scores
                    for decision in decisions:
                        username = decision['username']
                        score = decision['score']
                        if score > 0.98:
                            follow_by_username(auth, user_id, username)
                            print(f"user {username} has a high rizz of {score}, now following.")
                        else:
                            print(f"Score {score} for user {username} is below or equal to 0.97. Not following.")
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

    # Step 3: Generate short-term memory
    short_term_memory = generate_short_term_memory(recent_posts, external_context, llm_api_key)
    print(f"Short-term memory: {short_term_memory}")
    
    # Step 4: Create embedding for short-term memory
    short_term_embedding = create_embedding(short_term_memory, openai_api_key)
    # print(f"Short-term embedding: {short_term_embedding}")
    
    # Step 5: Retrieve relevant long-term memories
    long_term_memories = retrieve_relevant_memories(db, short_term_embedding)
    print(f"Long-term memories: {long_term_memories}")
    
    # Step 6: Generate new post
    new_post_content = generate_post(short_term_memory, long_term_memories, recent_posts, external_context, llm_api_key)
    print(f"New post content: {new_post_content}")

    # Step 7: Score the significance of the new post
    significance_score = score_significance(new_post_content, llm_api_key)
    print(f"Significance score: {significance_score}")
    
    # Step 8: Store the new post in long-term memory if significant enough
    # CHANGE THIS TO WHATEVER YOU WANT TO DETERMINE HOW RELEVANT A POST / SHORT TERM MEMORY NEEDS TO BE TO WARRANT A RESPONSE
    if significance_score >= 7:
        new_post_embedding = create_embedding(new_post_content, openai_api_key)
        store_memory(db, new_post_content, new_post_embedding, significance_score)
    
    # Step 9: Save the new post to the database
    # Update these values to whatever you want
    ai_user = db.query(User).filter(User.username == "lessdong").first()
    if not ai_user:
        ai_user = User(username="lessdong", email="lessdong@example.com")
        db.add(ai_user)
        db.commit()

    # THIS IS WHERE YOU WOULD INCLUDE THE POST_SENDER.PY FUNCTION TO SEND THE NEW POST TO TWITTER ETC
    # Only Bangers! lol 
    if significance_score >= 3:
        tweet_id = send_post(auth, new_post_content)
        print(tweet_id)
        if tweet_id:
            new_db_post = Post(content=new_post_content, user_id=ai_user.id, username=ai_user.username, type="text", tweet_id=tweet_id)
            db.add(new_db_post)
            db.commit()
    

    # FOLLOW USERS
    # follow_by_username(auth, user_id, 'ropirito')
    # USING WALLET
    # transfer_eth(private_key_hex, '0x0', 0.0)

    print(f"New post generated with significance score {significance_score}: {new_post_content}")


# if __name__ == "__main__":

#     db = next(get_db())
#     run_pipeline(
#         db,
#         openrouter_api_key="your_openrouter_api_key",
#         openai_api_key="your_openai_api_key",
#         news_api_key="your_news_api_key"
#     )