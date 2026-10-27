/*
 * 11 - Demo: all seven security rules fire in one program.
 * EXPECT: HARDCODED_CREDENTIAL 16 HIGH
 * EXPECT: INTEGER_OVERFLOW 25 MEDIUM
 * EXPECT: DANGEROUS_FUNC 32 HIGH
 * EXPECT: DANGEROUS_FUNC 33 HIGH
 * EXPECT: BUFFER_OVERFLOW 33 HIGH
 * EXPECT: BUFFER_OVERFLOW 34 HIGH
 * EXPECT: INTEGER_OVERFLOW 35 HIGH
 * EXPECT: UNINITIALIZED_VAR 37 HIGH
 * EXPECT: NULL_DEREFERENCE 38 HIGH
 * EXPECT: UNREACHABLE_CODE 41 LOW
 */

/* Rule 1: hardcoded credential */
char *db_password = "admin@123";

int process(int flag) {
    char name[8];
    int scores[3];
    int total;
    int *record;
    int big;
    /* Rule 2: integer overflow - 300 does not fit in a char */
    char grade = 300;

    record = 0;
    if (flag > 0) {
        total = flag;
    }

    gets(name);                                  /* Rule 3: dangerous function   */
    strcpy(name, "this name is far too long");   /* Rule 4: buffer overflow      */
    scores[5] = 1;                               /* Rule 4: index out of bounds  */
    big = 2147483647 + 1;                        /* Rule 2: integer overflow     */

    total = total + 1;                           /* Rule 5: uninitialized (data-flow) */
    big = *record;                               /* Rule 6: null deref (data-flow)    */

    return total;
    total = 0;                                   /* Rule 7: unreachable code (CFG)    */
}
