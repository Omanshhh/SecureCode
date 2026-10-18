/*
 * 04 - Buffer overflow: constant index past the end of an int[4].
 * EXPECT: BUFFER_OVERFLOW 12 HIGH
 */
int main() {
    int scores[4];
    int best;

    scores[0] = 90;
    scores[1] = 75;
    scores[3] = 60;
    scores[4] = 99;

    best = scores[0];
    return best;
}
