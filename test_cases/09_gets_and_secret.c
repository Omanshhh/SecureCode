/*
 * 09 - Two categories: gets() reading a line, and a hardcoded session token.
 * EXPECT: DANGEROUS_FUNC 11 HIGH
 * EXPECT: HARDCODED_CREDENTIAL 7 MEDIUM
 */
int read_name() {
    char *session_token = "f00dbabe";
    char name[32];
    int len;

    gets(name);
    len = 0;
    return len;
}
