/*
 * 01 - Dangerous function: strcpy into a fixed buffer.
 * The copy length is unknown, so this is a dangerous-call finding only.
 * EXPECT: DANGEROUS_FUNC 9 HIGH
 */
int main() {
    char buffer[8];
    char input[20];
    strcpy(buffer, input);
    return 0;
}
