/*
 * 08 - Unreachable code: the assignment after 'return' can never execute.
 * EXPECT: UNREACHABLE_CODE 14 LOW
 */
int clamp(int value) {
    int out;

    out = value;
    if (value > 100) {
        out = 100;
    }
    return out;

    out = 0;
}
