import logging
import sys
from app.runner import run

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    
    # Run the full pipeline!
    run()

if __name__ == "__main__":
    main()
