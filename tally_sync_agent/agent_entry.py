"""PyInstaller entry point: FieldTrackTallyAgent.exe <test-tally|test-backend|health|status|sync|daemon>."""
import multiprocessing

from tally_sync_agent.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
