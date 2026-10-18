/*
 * 06 - Null dereference: 'node' starts as null and is only pointed at real
 * storage on one branch.
 * EXPECT: NULL_DEREFERENCE 17 HIGH
 */
int lookup(int key) {
    int *node;
    int slot;
    int value;

    slot = 42;
    node = 0;

    if (key == 7) {
        node = &slot;
    }
    value = *node;
    return value;
}
