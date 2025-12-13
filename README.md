# Manga Fetcher

TUI and CLI tool for downloading manga from multiple sources.

Sources:

- kisslove (https://klz9.com)
- mangakatana (https://mangakatana.com)

## Setup

```bash
pip install -r requirements.txt
```

## TUI

```bash
python main.py
```

## CLI

Search:

```bash
python main.py search "one piece"
python main.py --source mangakatana search "one piece"
```

Show info and chapters:

```bash
python main.py info <slug>
python main.py --source mangakatana info <slug>
```

Download chapters by index range (1-based):

```bash
python main.py download <slug> --start 1 --end 5
python main.py --source mangakatana download <slug> --start 1 --end 5
```

Create CBZ files as well:

```bash
python main.py download <slug> --start 1 --end 5 --cbz
```
