import grp
import os
import pwd


def admin(user):
    try:
        pw = pwd.getpwnam(user)
    except KeyError:
        return False
    for g in ("sudo", "wheel"):
        try:
            gr = grp.getgrnam(g)
        except KeyError:
            continue
        if user in gr.gr_mem or pw.pw_gid == gr.gr_gid:
            return True
    return False


def pam_sm_authenticate(pamh, flags, argv):
    try:
        user = pamh.get_user(None)
    except pamh.exception:
        return pamh.PAM_USER_UNKNOWN
    if not user or user == "root":
        return pamh.PAM_IGNORE
    try:
        caller = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return pamh.PAM_IGNORE
    if caller != user or not admin(user):
        return pamh.PAM_IGNORE
    try:
        resp = pamh.conversation(pamh.Message(pamh.PAM_PROMPT_ECHO_ON, "Пароль не нужен. Нажмите «OK», чтобы подтвердить действие:"))
    except pamh.exception:
        return pamh.PAM_AUTH_ERR
    if resp is None:
        return pamh.PAM_AUTH_ERR
    return pamh.PAM_SUCCESS


def pam_sm_setcred(pamh, flags, argv):
    return pamh.PAM_SUCCESS
