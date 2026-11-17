# PyBot-Web

**A rule-based Python chatbot with optional DuckDuckGo web search.**

PyBot-Web extends [Hugging Face's PyBot](https://github.com/huggingface/pybot) so it can look up current public information and include search snippets and source links in its replies. It keeps PyBot's original approach: Python rules, regular expressions, lookup tables, and conversation memory. No LLM inference, neural networks, model downloads, or model APIs are added.

Web search is **off by default**. The bot still works locally without the optional search dependency or an internet connection.

## What's new

- **Optional internet access through `ddgs`.** Searches use the DuckDuckGo backend, with no API key required.
- **Automatic search routing.** Rules recognize supported questions about current company leaders, news, weather, market prices, and software releases.
- **Explicit searches.** Ask "search the web for ...", "search for ...", or "look up ..." to search other topics.
- **Readable, attributed results.** Replies show up to three result titles, short snippets, and source URLs. Snippets are labeled as unverified excerpts.
- **Graceful failures.** Missing dependencies, connection failures, timeouts, and empty results produce an explanation instead of breaking the conversation.
- **Existing local responses.** Arithmetic, date calculations, cooking advice, greetings, and conversation recall stay with PyBot's existing modules. Emergency responses and ongoing safety threads stay local.
- **CLI controls and mocked tests.** Enable search with `--web-search` or `PYBOT_WEB_SEARCH`; force it off with `--no-web-search`. Automated tests cover the adapter, routing, response pipeline, and CLI without making external search calls.

The original runtime and arbiter are unchanged. The Python module and command names remain `pybot` for compatibility.

## Quick start

Clone this fork and run it locally:

Offline PyBot needs Python 3.8 or newer and no third-party packages. Optional web search needs Python 3.10 or newer and the `ddgs` package. Neither mode downloads or runs a model.

```sh
git clone https://github.com/simoneprezioso/pybot-web.git
cd pybot-web
python -m pybot
```

That starts a chat in your terminal. The existing PyBot logo and `pybot` commands are retained for compatibility:

```text
    ____        ____        __
   / __ \__  __/ __ )____  / /_
  / /_/ / / / / __  / __ \/ __/
 / ____/ /_/ / /_/ / /_/ / /_
/_/    \__, /_____/\____/\__/
      /____/

A chatbot written in plain Python. No weights, no training, just rules.
Type a message and press Enter. /reset starts a new conversation, /exit quits.

user: hi, i'm Sam
pybot: Nice to meet you, Sam. What can I help with?

user: my kettle is full of limescale, how do i get rid of it?
pybot: Half fill the kettle with equal parts water and white vinegar, or a sachet of citric acid, boil it and leave it half an hour, then tip it out and boil fresh water twice before you use it again. In a hard-water area do it every couple of months: the scale forms because hard water leaves calcium behind as it boils, and a thick layer makes the kettle slow and puts a scum on the tea.

user: how long does that take
pybot: Half an hour.

user: what's my name?
pybot: You're Sam.
```

Type `/reset` to clear the screen and start a new conversation, `/help` for commands, and `/exit` to quit. PyBot-Web takes a few seconds to load the original rule modules. Search requests add network latency when enabled.

To ask one question and exit, or to pipe messages in and get one reply per line:

```sh
python -m pybot -p "Why do onions make you cry?"
echo "how long should i boil an egg" | python -m pybot
```

| Option | What it does |
|---|---|
| `-p TEXT`, `--prompt TEXT` | reply to this one message and exit |
| `-i`, `--interactive` | with `-p`, keep chatting after the first reply |
| `-s N`, `--seed N` | seed local wording choices; live search results can still change |
| `-v`, `--verbose` | after each reply, show the module that produced it and the time it took |
| `--web-search` | enable optional DuckDuckGo search for this invocation |
| `--no-web-search` | disable search even when `PYBOT_WEB_SEARCH` enables it |

For a `pybot` command you can run from anywhere, install the clone with `pip install .`.

## Optional internet search

Search is off by default. Install the extra from this repository using Python 3.10 or newer:

```sh
python -m pip install ".[web]"
python -m pybot --web-search -p "Who is the current CEO of Microsoft?"
python -m pybot --web-search -p "What happened in AI news today?"
python -m pybot --web-search -p "Search the web for Python release notes"
```

For an interactive chat with search enabled:

```sh
python -m pybot --web-search
```

Even with search enabled, `python -m pybot --web-search -p "What is 2 + 2?"` uses the existing local calculator and makes no search request.

Installing `ddgs` directly (`python -m pip install "ddgs>=9,<10"`) also works. The offline package still supports Python 3.8 and 3.9; those versions do not install `ddgs` through the extra and cannot use web search.

You can also enable search through the environment, including when using `python -m bot` or `bot.runtime.reply`:

```sh
export PYBOT_WEB_SEARCH=1
python -m pybot
```

In PowerShell:

```powershell
$env:PYBOT_WEB_SEARCH = "1"
python -m pybot
```

Use `--no-web-search` to override that environment setting for one invocation. With search disabled, no queries are sent and `ddgs` is not imported. The CLI flags apply only to the current invocation and restore the previous environment setting when `main()` returns.

Accepted enabled environment values are `1`, `true`, `yes`, and `on`, ignoring case. Other values disable search.

The search module uses deterministic rules to recognize public information that can change, such as company leaders, recent news, weather, and software releases. An explicit request such as "search the web for ..." also triggers search. Arithmetic ("What is 2 + 2?"), date calculations, ordinary cooking advice, greetings, and questions about the conversation keep their existing local responses. These rules deliberately cover a limited set of question forms; use an explicit web-search request for other topics.

Responses present a short list of titles, excerpts from search snippets, and source URLs. They label these as search results rather than verified facts: snippets can be stale, incomplete, or contradictory. PyBot does not infer an unsupported answer, verify page contents, or use an LLM to summarize them. Check the linked sources for confirmation, especially for current information.

For example, this is an **illustrative format**, not a live search result:

```text
Search results for "example query" (snippets, not independently verified): [1] Example title: An excerpt from the search result. Source: https://example.org/page
```

The adapter lazily imports [`ddgs`](https://github.com/deedy5/ddgs), explicitly selects its `duckduckgo` backend, and requests at most three results with a five-second client timeout. That timeout is not a guaranteed deadline for the entire chatbot turn. The adapter adds no retry loop. Missing dependencies, timeouts, network failures, and empty results produce a short explanation instead of breaking the conversation. The library is unofficial and free to use without an API key; DuckDuckGo may throttle, block, or return no results, so successful retrieval is not guaranteed. Enabling search sends eligible query text to the search service.

## Testing

Run the existing CLI tests and the new mocked search tests with:

```sh
python -m unittest discover -s tests
```

Automated search tests replace external calls and require neither internet access nor `ddgs`.

Coverage includes current-information questions, explicit requests, local questions that must not search, missing dependencies, network failures, timeouts, empty results, source formatting, safety precedence, conversation memory, and CLI configuration.

## What is in this repository

| Path | What it holds |
|---|---|
| `bot/` | PyBot's original rule-based modules, plus the optional search adapter and module |
| `bot/search.py` | optional `ddgs` adapter, result cleanup, and error handling |
| `bot/modules/web_search.py` | rule-based search routing, safety checks, and excerpt formatting |
| `pybot.py` | the command line shown above. It contains no chatbot logic |
| `tests/` | CLI, search adapter, and response-pipeline tests |
| `assets/` | the banner and the chart |

Every turn, each module in `bot/modules/` may propose a reply, and an arbiter (`bot/modules/arbiter.py`) picks the one you get. The modules build on four shared parts:

| Part | Where | Lines |
|---|---|---:|
| Understanding engine: what you typed and meant, with typos, chat-speak, the topic and what "it" refers to | `bot/understanding/` | 25,000 |
| Memory store: what you and PyBot have said so far | `bot/memory/` | 109,000 |
| Knowledge base: facts about the world, kept as data | `bot/knowledge/` | 317,000 |
| Response composer: how a reply is phrased, and what to say when nothing fits | `bot/compose/` | 104,000 |

The modules themselves are another 81,000 lines.

### How search fits the existing architecture

`bot/runtime.py` discovers modules automatically and runs four phases for each input. First, `observe(text, memory)` hooks update the shared understanding and memory. Then, `respond(text, memory)` hooks propose replies using separate memory copies. The arbiter selects a candidate, whose memory copy becomes the conversation's memory. Finally, `after(text, reply, memory)` hooks run and the runtime records the turn.

`bot/modules/answers.py` already answers calculations and knowledge-base questions. The new `bot/modules/web_search.py` participates in the same proposal system and delegates external access to `bot/search.py`. Its narrow routing rules and existing arbiter claim hooks give eligible current-information questions a search response. The hooks only inspect the query and configuration; they never perform network requests. Its priority is below the existing safety band. Before network access, it also checks existing emergency rules on an isolated memory copy, preserving random state, so emergency replies do not wait for a search. Existing safety threads stay local. The runtime and arbiter require no changes, and all parsing, selection, and response formatting remain ordinary Python rules.

## Credits and license

The original rule-based chatbot was created by [Hugging Face's PyBot project](https://github.com/huggingface/pybot). This fork adds optional web search and its integration, configuration, documentation, and tests. The [upstream Hugging Face demo](https://huggingface.co/spaces/HuggingFaceSwarms/PyBot) demonstrates the original PyBot, not this fork's search feature.

Apache License 2.0. See [LICENSE](LICENSE).
