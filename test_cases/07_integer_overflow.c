/*
 * 07 - Integer overflow: a constant expression past INT_MAX, and an unchecked
 * size product passed to malloc.
 * EXPECT: INTEGER_OVERFLOW 8 HIGH
 * EXPECT: INTEGER_OVERFLOW 11 MEDIUM
 */
int allocate(int items) {
    int limit = 2147483600 + 100;
    int *table;

    table = malloc(items * 8);
    return limit;
}
