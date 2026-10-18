/*
 * 05 - Uninitialized variable: 'sum' is only assigned when the loop body runs,
 * then read after the loop.
 * EXPECT: UNINITIALIZED_VAR 16 HIGH
 */
int average(int n) {
    int sum;
    int i;
    int result;

    i = 0;
    while (i < n) {
        sum = i;
        i = i + 1;
    }
    result = sum / 2;
    return result;
}
