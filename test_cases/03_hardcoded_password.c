/*
 * 03 - Hardcoded credentials: a global password and a local API key.
 * 'server_name' is a plain string and must NOT be flagged.
 * EXPECT: HARDCODED_CREDENTIAL 7 HIGH
 * EXPECT: HARDCODED_CREDENTIAL 10 HIGH
 */
char *root_password = "toor";

int login() {
    char *stripe_api_key = "sk_test_51Hx9";
    char *server_name = "auth.internal";
    int ok;

    ok = 1;
    return ok;
}
