"""Spúšťač aplikácie (aj vstupný bod pre PyInstaller)."""
import multiprocessing
import sys

if __name__ == "__main__":
    # v zabalenom .exe musí byť pred čímkoľvek iným (procesy na čítanie strán)
    multiprocessing.freeze_support()
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        from kompletacia.selftest import main as selftest
        sys.exit(selftest(sys.argv[2]))
    from kompletacia.gui import main
    main()
