"""Pure validation of terminal receipts for an explicitly expected attempt."""
import re


UNCONFIRMED = ('Prozessende ist noch nicht sicher bestätigt; keine parallele Wiederaufnahme. '
               'Aufräumen abwarten oder Prozessstatus prüfen.')


def validate_receipt(receipt, *, ticket, command_sha256, supervisor_pid=None):
    """Validate cleanup only; callers retain their job/path/config bindings."""
    if (not isinstance(receipt, dict) or not isinstance(ticket, str) or not ticket
            or not isinstance(command_sha256, str) or not re.fullmatch('[a-f0-9]{64}', command_sha256)
            or type(receipt.get('schema_version')) is not int or receipt['schema_version'] != 1
            or receipt.get('ticket') != ticket or receipt.get('command_sha256') != command_sha256
            or receipt.get('status') != 'finished' or receipt.get('cleanup_confirmed') is not True
            or receipt.get('cleanup_scope') not in ('windows_job', 'process_group')
            or type(receipt.get('supervisor_pid')) is not int or receipt['supervisor_pid'] <= 0
            or type(receipt.get('exit_code')) is not int
            or (supervisor_pid is not None and (type(supervisor_pid) is not int or supervisor_pid <= 0
                                               or receipt['supervisor_pid'] != supervisor_pid))):
        raise ValueError(UNCONFIRMED)
    return dict(receipt)
