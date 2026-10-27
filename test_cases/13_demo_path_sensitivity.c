/*
 * 13 - Demo: why data-flow analysis is path-sensitive.
 *   'safe'  is assigned on BOTH branches  -> not reported
 *   'risky' is assigned on ONE branch     -> reported
 *   'q'     always points at real storage -> not reported
 *   'p'     is still null on the else path -> reported
 * The symbol table marks every one of these as initialized.
 * EXPECT: UNINITIALIZED_VAR 31 HIGH
 * EXPECT: NULL_DEREFERENCE 32 HIGH
 */
int decide(int flag) {
    int safe;
    int risky;
    int value;
    int *p;
    int *q;
    int out;

    value = 10;
    p = 0;
    q = &value;

    if (flag > 0) {
        safe = 1;
        risky = 1;
        p = &value;
    } else {
        safe = 2;
    }

    out = safe + risky;
    out = out + *p + *q;
    return out;
}
