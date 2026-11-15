"""Composition root for the local browser application."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import logging
from pathlib import Path
import webbrowser

from startkartenleser.application.use_cases import StartkartenUseCases
from startkartenleser.browser_server import BrowserServer
from startkartenleser.browser_workflow import BrowserWorkflow
from startkartenleser.infrastructure.application_lock import application_lock
from startkartenleser.infrastructure.correction_policy import (
    DEFAULT_CONFIG_PATH, load_app_configuration,
)
from startkartenleser.infrastructure.image_store import ManagedImageStore
from startkartenleser.infrastructure.paths import AppDataPaths
from startkartenleser.infrastructure.sqlite_repositories import SqliteRepositories
from startkartenleser.infrastructure.workflow_adapters import (
    ConservativeCheckboxProposer, LazyDEHTRLineRecognizer, TemplateCardAligner,
)
from startkartenleser.localization import TextCatalog


def main() -> None:
    parser = argparse.ArgumentParser(description="StartkartenLeser: local browser UI")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser")
    parser.add_argument("--port", type=int, default=0, help="Loopback port (default: automatic)")
    parser.add_argument("--data-dir", type=Path, help="Use a separate local data directory")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    logging.basicConfig(level=logging.INFO)
    text = TextCatalog.load()
    paths = AppDataPaths(args.data_dir) if args.data_dir else AppDataPaths.default()
    paths.ensure()
    with ExitStack() as stack:
        try:
            stack.enter_context(application_lock(paths.root))
        except OSError as error:
            raise SystemExit(text.text("browser.already_running")) from error
        configuration = load_app_configuration(paths.prepare_config(DEFAULT_CONFIG_PATH))
        recognizer = LazyDEHTRLineRecognizer()
        stack.callback(recognizer.close)
        images = ManagedImageStore(paths.images)
        repositories = SqliteRepositories(paths.database, images)
        stack.callback(repositories.close)
        repositories.cleanup_storage_orphans()
        use_cases = StartkartenUseCases(
            sessions=repositories, cards=repositories, images=images,
            aligner=TemplateCardAligner(), recognizer=recognizer,
            checkbox_proposer=ConservativeCheckboxProposer(),
            retention=repositories, correction_policy=configuration.correction_policy,
        )
        workflow = BrowserWorkflow(
            repositories, images, use_cases, text, strokes=configuration.strokes,
        )
        server = BrowserServer(workflow, args.port)
        stack.callback(server.server_close)
        stack.callback(workflow.cancellation.set)
        print(text.text("browser.launch", url=server.launch_url), flush=True)
        print(text.text("browser.lifetime"), flush=True)
        if not args.no_browser and not webbrowser.open(server.launch_url):
            logging.warning(text.text("browser.open_failed"))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print(text.text("browser.stopped"), flush=True)


if __name__ == "__main__":
    main()
