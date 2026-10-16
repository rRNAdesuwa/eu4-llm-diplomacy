[English](Readme_EN.md) | [简体中文](Readme.md)

# EU4 LLM Diplomacy

This is an experimental project connecting **Europa Universalis IV** with large language models (LLMs).

The long-term goal of this project is to let an LLM take over the diplomatic decision-making of selected AI-controlled countries, while continuing to leave military, economic, and other game systems under the control of Europa Universalis IV's native AI.

Players will be able to negotiate directly with LLM-controlled countries through text: promise benefits, issue threats, discuss alliances, negotiate peace, deceive opponents, and betray previous commitments. In short, the goal is to create a richer and more realistic diplomatic experience.

We have confirmed that the diplomatic interfaces exposed by the game itself are very limited. In order to expose these operations to an external LLM, we have chosen a development path based on reverse engineering, DLL injection, and runtime hooking. This project is exploring how to achieve that goal, and our current experiments have given us considerable confidence in the feasibility of this approach.

## Current Status

This project is currently in **early experimental development**.

2026-10-16: [EU4 1.37.5 research checkpoint](docs/research-20261016-en.md) is now available with 120 TAG action bindings, direct runtime observers and a 60-record war/peace evidence index. The original batch contains 41 dispatches, 77 refusals and 2 unknowns; historical selected effects cover 48 actions, with 44 persistence records. Full effect validation, a callable 1.37.5 war/peace executor and LLM integration remain incomplete. Research is paused; this is a source snapshot. See the [tool catalog](docs/runtime-capability-map-1375-v8.json) and [Chinese evidence report](docs/research-20261016.md).

The following are historical capabilities validated on EU4 1.37.4:

- Exporting part of the game state through a custom Mod;
- Intercepting the native AI's authority to declare war and negotiate peace, while establishing an authorization path for externally initiated peace actions;
- Executing some diplomatic actions externally: allowing an LLM-controlled country to declare war on the player or another country, and later negotiate peace while demanding monetary reparations;

The following areas are not yet complete:

- Full reverse engineering of diplomatic actions, including vassalization, royal marriages, improving relations, guarantees, spy networks, and many others, and exposing all of them through external interfaces;
- Improving LLM access to game information and defining proper information boundaries;
- Removing all native AI diplomatic authority;
- A production-ready LLM interface;
- Improving the prompts used for LLM-controlled countries, and designing diplomatic decision-making Agents, context management, long-term memory, negotiation, and strategic planning;
- After all major technical issues are solved, substantial work will still be needed to improve actual gameplay;
- Finally, the project still needs to become stable and compatible across game versions.

For the current research status, experiment records, and technical validation, see `HANDOFF.md`, `PLAN.md`, and `VALIDATION.md`.

## Getting and Using the Project

1. Clone the repository, or simply give the repository URL to your Agent together with your local EU4 installation directory (the folder containing `eu4.exe`) and user-data directory (usually `C:\Users\<your username>\Documents\Paradox Interactive\Europa Universalis IV`). The Agent can then assist with environment configuration, building, and reproducing experiments.

2. If you prefer to do it yourself, clone the repository, complete your local setup according to the [Path Configuration](docs/%E8%B7%AF%E5%BE%84%E9%85%8D%E7%BD%AE.md) guide, and then follow the [Reproduction Procedure](docs/人工实验与日志读取流程.md).

> [!WARNING]
> **Early Development / Experimental Project**
>
> This project is still under active research and development. It is not a finished or stable mod, and there is currently no officially supported public release.
>
> The main purpose of making this repository public is open development, technical discussion, collaboration, and reproducible experimental research—in other words, recruiting contributors and collaborating, if we manage to find any. This is still far from being a playable release.
>
> The historical release targets Europa Universalis IV 1.37.4; the newer research source targets a separately pinned 1.37.5 executable. They use different profiles and must not share DLL addresses or validation claims. The project relies on reverse engineering, DLL injection, and hooking. Compatibility with other versions is not guaranteed. Running experimental builds may cause game crashes, save corruption, or other unexpected behavior. Please use disposable test saves only, or make sure reliable backups are available.

## Contributing

This project is still in an early research and development stage, and developers interested in EU4 modding, reverse engineering, programming, or LLM Agents are very welcome to participate. Contributors are not expected to understand the entire project. Even if your programming experience is limited, as long as you are interested, have some spare time, and have some AI credits available (😂), you can probably still make a useful contribution.

Possible areas of contribution include, but are not limited to:

- **Project coordination and management**: if you have experience collaborating with others on software projects, you are welcome to help coordinate the project as a whole;
- **EU4 reverse engineering**: analyze diplomacy-related internal objects, functions, Action types, call chains, and version differences;
- **Diplomatic interface expansion**: continue implementing alliances, royal marriages, guarantees, military access, peace terms, and other diplomatic actions;
- **LLM Agent development**: design diplomatic decision-making Agents, context management, long-term memory, negotiation, and strategic planning;
- **Information-boundary design**: study how to provide the LLM only with information that it could reasonably know under the game's rules, avoiding an "omniscient AI" created by reading the entire save file;
- **Version compatibility**: study internal structural changes between different EU4 versions and develop compatibility approaches;
- **Testing and reproduction**: reproduce experiments in different environments, validate results, and improve automated testing;
- **Documentation**: organize reverse-engineering findings, architecture documentation, reproduction procedures, and developer documentation.

Contributors are not expected to implement complete features in a single contribution. Experimental results, reverse-engineering notes for a single function, testing on different EU4 versions, or participation in technical discussions are all very welcome.

If you are interested in contributing, you can:

1. Leave me your contact information!
2. Create a GitHub Issue to discuss ideas or experimental results;
3. Participate in existing Issue discussions;
4. Fork the repository and submit a Pull Request;
5. Submit a small reproduction experiment or documentation improvement;
6. ...

## Disclaimer

This project is an unofficial modification and research project for Europa Universalis IV.

Europa Universalis IV, Paradox Interactive, and all related trademarks, game assets, executable code, and other intellectual property are the property of Paradox Interactive AB and/or their respective rights holders.

This project is not affiliated with, endorsed by, sponsored by, or otherwise associated with Paradox Interactive AB.

The license used by this repository applies only to original code and documentation created by this project's contributors. It does not grant any rights to Europa Universalis IV, its executable files, game data, assets, or any other third-party intellectual property.

## Technical and Security Notice

This project uses DLL injection, runtime hooking, and reverse-engineered internal game interfaces in order to extend Europa Universalis IV for single-player modding and research purposes.

These techniques are also used by debuggers, modding frameworks, security tools, and malicious software. As a result, antivirus or endpoint-security products may classify project binaries or the injector as suspicious.

Users are encouraged to build the project themselves from the source code published in this repository. Precompiled binaries should only be obtained from official Releases of this repository.

The native bridge is explicitly version-dependent. After an Europa Universalis IV update, internal addresses, data structures, or hook locations may become invalid and may cause game crashes, save corruption, or other unexpected behavior.

## Intended Use

This project is intended only for local, single-player Europa Universalis IV modding and research.

This project is not intended to:

- bypass DRM or game ownership checks;
- unlock, circumvent, or bypass paid DLC restrictions;
- interfere with Paradox or third-party online services;
- obtain another user's credentials or private information;
- provide unfair advantages in multiplayer games.

## License

Unless otherwise stated, original source code in this repository is licensed under the MIT License.

Third-party components and related intellectual property remain subject to their respective licenses and terms.