/*
 * 12 - Demo: the same program as 11 with every bug fixed.
 * No EXPECT lines: the engine must report ZERO findings.
 */
int process(int flag) {
    char name[32];
    int scores[3];
    int total;
    int *record;
    int value;
    int big;
    char *db_password;
    char grade = 65;

    db_password = getenv("DB_PASSWORD");   /* secret read at runtime, not hardcoded */
    value = 7;
    record = &value;                       /* points at real storage, never null    */
    total = 0;                             /* assigned on every path                */
    if (flag > 0) {
        total = flag;
    }

    snprintf(name, 32, "user%d", flag);    /* bounded write, not gets/strcpy        */
    scores[2] = 1;                         /* index within 0..2                     */
    big = flag + 1;

    total = total + 1;
    big = *record;

    return total;
}
