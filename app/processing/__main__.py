# %%
import argparse

from app.processing.cleaner import clean

# Edit these strings to test different messy inputs!
TEST_BLOG_HTML = """
<p>Welcome to the   <b>DailyDigest</b>  newsletter!</p> 

 <br> <a href='#'>Click here to subscribe.</a> <p>  &amp; that is all! &#8220;Thanks&#8221;  </p>
"""

TEST_YOUTUBE_TRANSCRIPT = """
[00:00:00] Hi everyone, uh, welcome back to the channel. 
[00:00:05] [Music] 
[00:00:10] Today, um, we are going to look at the new model architecture. 
[00:00:15] So, if you look at the self-attention mechanism, hmm, it's pretty wild. 
[00:00:22] [Applause] 
[00:00:25] Yeah, exactly. [Laughter]
"""

def run_test(source_type: str, raw_input: str):
    print(f"\n--- Cleaner Test Mode ({source_type.upper()}) ---")
    print("="*50)
    
    try:
        cleaned, tokens = clean(raw_input, source_type=source_type)
        print("RAW INPUT:")
        print(raw_input.strip())
        print("\nCLEANED OUTPUT:")
        print(cleaned)
        print(f"\n--- METRICS ({source_type.upper()}) ---")
        print(f"Raw length:     {len(raw_input)} chars")
        print(f"Cleaned length: {len(cleaned)} chars")
        print(f"Estimated:      ~{tokens} tokens")
    except Exception as e:
        print(f"Error during cleaning: {e}")

def main():
    run_test("blog", TEST_BLOG_HTML)
    print("\n\n" + "*"*60)
    run_test("youtube", TEST_YOUTUBE_TRANSCRIPT)

if __name__ == "__main__":
    main()
# %%
