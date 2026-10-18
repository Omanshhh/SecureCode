/*
 * 02 - Dangerous functions: sprintf builds a shell command, system runs it.
 * EXPECT: DANGEROUS_FUNC 11 HIGH
 * EXPECT: DANGEROUS_FUNC 12 HIGH
 */
int run_backup(char *target) {
    char command[64];
    int status;

    status = 0;
    sprintf(command, "tar czf backup.tgz %s", target);
    system(command);
    return status;
}
