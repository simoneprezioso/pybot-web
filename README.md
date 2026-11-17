# PyBot-Web

**A rule-based Python chatbot with on-demand web search.**

PyBot-Web extends [Hugging Face's PyBot](https://github.com/huggingface/pybot) with internet search through [`ddgs`](https://github.com/deedy5/ddgs). It keeps the original Python rules, regular expressions, lookup tables, and conversation memory. No LLM inference, neural networks, model downloads, or model APIs are added.

Type **`/web <query>`** to search. Automatic searches are off by default, so ordinary conversation stays local unless you explicitly request a search or enable automatic routing.

## What's new

- **A short search command.** `/web AI news`, `/web pancake recipe`, and `/web what to do in Rome` retrieve titles, snippets, and source links. `/web` by itself shows usage without making a request.
- **DuckDuckGo-first search with fallbacks.** The `ddgs` adapter tries available providers in order: DuckDuckGo, Yahoo, then Startpage. It moves on when a provider fails or returns no usable results. No API keys are required.
- **Optional automatic routing.** With `--web-search`, rules recognize supported current-information questions about company leaders, news, weather, market prices, and software releases. Named-person questions can search when local knowledge has no answer.
- **Readable, attributed excerpts.** Replies show up to three result titles, short snippets, and source URLs, labeled as unverified excerpts.
- **Graceful failures.** Missing dependencies, connection failures, timeouts, and empty results produce an explanation instead of breaking the conversation.
- **Existing local behavior.** Arithmetic, date calculations, cooking advice, greetings, and conversation recall continue to use PyBot's existing modules. Emergency responses and ongoing safety threads stay local.

The original runtime and arbiter are unchanged. The Python module and command names remain `pybot` for compatibility.

## Quick start

Use **Python 3.10 or newer** for internet search:

```sh
git clone https://github.com/simoneprezioso/pybot-web.git
cd pybot-web
python -m pip install ".[web]"
python -m pybot
```

Then enter a search command in the chat:

```text
user: /web AI news
user: /web pancake recipe
user: /web what to do in Rome
```

These are example requests, not captured live search results. The reply contains short search excerpts and source links when a provider returns usable results.

For an existing clone, run these commands from its `pybot-web` folder:

```sh
git pull --ff-only
python -m pip install ".[web]"
python -m pybot
```

The interactive startup shows the search configuration. By default it says:

```text
Automatic web search is off. Use /web <query> for a one-off search.
```

`/web` is an explicit request to send that query to the search service. Installing the dependency alone does not cause ordinary messages to be sent. If it is missing, a search request explains how to install it.

## Search commands and CLI

| Command | What it does |
|---|---|
| `/web QUERY` | search for any natural-language query |
| `/web` | show search usage without making a request |
| `/reset` | clear the terminal and start a new conversation |
| `/help` | show the available chat commands |
| `/exit` | quit |

You can also search once and exit, or send a search through piped input:

```sh
python -m pybot -p "/web AI news today"
echo "/web pancake recipe" | python -m pybot
```

One-shot and piped modes print only replies. Interactive startup status is displayed again after `/reset` in a terminal. The existing PyBot logo is retained.

| CLI option | What it does |
|---|---|
| `-p TEXT`, `--prompt TEXT` | reply to one message and exit |
| `-i`, `--interactive` | with `-p`, keep chatting after the first reply |
| `-s N`, `--seed N` | seed local wording choices; live results can still change |
| `-v`, `--verbose` | show the module and elapsed time after each reply |
| `--web-search` | enable automatic searches for supported questions |
| `--no-web-search` | disable all web requests, including `/web` |

For a `pybot` command available from other directories, install the clone with `python -m pip install ".[web]"`.

## Optional automatic search

Start with `--web-search` if you want supported current-information questions to search without typing `/web`:

```sh
python -m pybot --web-search
python -m pybot --web-search -p "Who is the current CEO of Microsoft?"
python -m pybot --web-search -p "What's going on in AI today?"
python -m pybot --web-search -p "Who is Elon Musk?"
```

The startup will say `Automatic web search is enabled.` when the dependency is available. Enabled status describes configuration, not proof that a provider is reachable. You can ask `Can you search the internet?` to check configuration without making a search request.

Automatic routing uses deliberately narrow rules. Arithmetic ("What is 2 + 2?"), date calculations, ordinary cooking advice, greetings, and conversation recall stay local. Use `/web` to search other topics explicitly, including topics the bot could answer locally. Older phrases such as "search the web for ...", "search for ...", and "look up ..." remain supported when automatic search is enabled.

You can enable automatic search through the environment, including with `python -m bot` or `bot.runtime.reply`:

```sh
export PYBOT_WEB_SEARCH=1
python -m pybot
```

In PowerShell:

```powershell
$env:PYBOT_WEB_SEARCH = "1"
python -m pybot
```

Values `1`, `true`, `yes`, and `on` enable automatic search, ignoring case. With the variable unset or empty, automatic search is off and `/web` remains available. Values `0`, `false`, `no`, and `off` explicitly block all web requests, including `/web`. CLI flags override the environment for the current invocation and restore the previous value when `main()` returns.

## Offline use and requirements

For fully offline chat, run:

```sh
python -m pybot --no-web-search
```

This also blocks `/web` requests and overrides an enabled environment setting. No queries are sent and `ddgs` is not imported.

Offline PyBot supports Python 3.8 or newer without third-party packages. The optional web feature needs Python 3.10 or newer and `ddgs>=9,<10`; the `web` extra installs it only on supported Python versions. Installing that package directly also works:

```sh
python -m pip install "ddgs>=9,<10"
```

## Results, providers, and limitations

Responses present titles, excerpts from search snippets, and source URLs. Snippets can be stale, incomplete, or contradictory. PyBot-Web labels them as unverified search results, does not verify page contents, and does not infer an unsupported answer or use an LLM to summarize them. Check linked sources for confirmation.

This is an **illustrative format**, not a live search result:

```text
Search results for "example query" (snippets, not independently verified): [1] Example title: An excerpt from the search result. Source: https://example.org/page
```

The adapter tries at most three providers in order: **DuckDuckGo -> Yahoo -> Startpage**, stopping at the first one with usable, cleaned results. Unavailable or disabled providers are skipped. It checks the installed `ddgs` provider registry before requesting a search; if that check fails, it sends no requests. It never switches to the library's unrestricted automatic provider selection. Each available provider is attempted at most once per search, with a five-second HTTP-client timeout. The total turn can take longer than five seconds, and those client timeouts are not a guaranteed whole-turn deadline. A freshness filter is applied to queries such as "today" when supported by the provider.

This is an unofficial integration. Provider availability varies with the installed library, and providers can throttle, block automated requests, or return empty results. PyBot-Web does not bypass CAPTCHAs. If no provider returns usable results, it reports the failure instead of inventing an answer. A manual `/web` request or an eligible automatically routed message may send its query text to the available DuckDuckGo, Yahoo, and Startpage providers in that order.

## Testing

Run the CLI, adapter, routing, and response-pipeline tests with:

```sh
python -m unittest discover -s tests
```

Automated search tests mock external calls and require neither internet access nor `ddgs`. They cover current-information questions, explicit searches, local responses, dependency failures, network failures, timeouts, empty results, source formatting, safety precedence, conversation memory, and CLI configuration.

## Architecture

`bot/runtime.py` automatically discovers modules in `bot/modules/`. Each turn runs shared `observe` hooks, then gathers `respond` proposals on isolated memory copies. The arbiter chooses a reply and its memory copy. Finally, `after` hooks run and the runtime records the turn.

| Path | Responsibility |
|---|---|
| `bot/modules/web_search.py` | `/web`, configuration, rule-based routing, safety checks, and excerpt formatting |
| `bot/search.py` | optional `ddgs` adapter, provider fallbacks, result cleanup, and error handling |
| `bot/modules/answers.py` | existing calculations and knowledge-base answers |
| `bot/understanding/` | input normalization, topics, and references |
| `bot/memory/` | conversation memory |
| `bot/knowledge/` | local facts and calculations |
| `bot/compose/` | rule-based response wording |
| `pybot.py` | CLI and interactive chat |

The search module uses existing arbiter claim hooks and a priority below the safety band. The hooks inspect queries and configuration without making network requests. Before network access, existing emergency rules are checked on an isolated memory copy while preserving random state; ongoing safety threads stay local. No runtime or arbiter changes are required.

## Credits and license

The original chatbot was created by [Hugging Face's PyBot project](https://github.com/huggingface/pybot). This fork adds optional web search and its integration, configuration, documentation, and tests. The [upstream Hugging Face demo](https://huggingface.co/spaces/HuggingFaceSwarms/PyBot) demonstrates the original PyBot, not this fork's search feature.

Apache License 2.0. See [LICENSE](LICENSE).
