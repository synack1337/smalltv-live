/*
 * SmallTV Live.app launcher.
 *
 * Runs the host (`python -m smalltv_live run`) as a child process. Starting it from an app bundle lets
 * macOS attribute local network access to "SmallTV Live", which can then be allowed in
 * System Settings > Privacy & Security > Local Network.
 *
 * PYTHON_PATH is set at build time by install.sh. Output goes to ~/Library/Logs/SmallTV Live.log.
 */
#include <fcntl.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef PYTHON_PATH
#error "build with -DPYTHON_PATH=\"/path/to/venv/bin/python\""
#endif

extern char **environ;
static pid_t child = 0;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

int main(void) {
    const char *home = getenv("HOME");
    if (home && home[0] == '/') {
        char log[1024];
        int n = snprintf(log, sizeof log, "%s/Library/Logs/SmallTV Live.log", home);
        /* HOME belongs to the user running the app; O_NOFOLLOW refuses a symlink planted at the log path. */
        int fd = (n > 0 && (size_t)n < sizeof log)
                     ? open(log, O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW | O_CLOEXEC, 0600)
                     : -1;
        if (fd >= 0) {
            dup2(fd, STDOUT_FILENO);
            dup2(fd, STDERR_FILENO);
            close(fd);
        }
    }
    signal(SIGTERM, forward);
    signal(SIGINT, forward);

    char *argv[] = {PYTHON_PATH, "-m", "smalltv_live", "run", NULL};
    if (posix_spawn(&child, PYTHON_PATH, NULL, NULL, argv, environ) != 0) {
        perror("smalltv-live: cannot start " PYTHON_PATH);
        return 1;
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {
        /* interrupted by a forwarded signal: keep waiting for the child */
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
