"""Deterministic information-loss review of verified saved intermediates."""
from diagnostic_cli import run_diagnostic
from information_loss_core import analyze_information_loss, render_information_loss
from progress_events import track_module


@track_module
def main(argv=None):
    run_diagnostic('information_loss', 'information_loss', 'Referenzübergänge und Prüfhinweise zu möglichem Informationsverlust',
                   lambda snapshot: analyze_information_loss(snapshot, snapshot['dependency_edges']),
                   render_information_loss, argv)


if __name__ == '__main__':
    main()
