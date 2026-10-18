/*
 * 10 - Clean program: bounded loops, every variable assigned before use.
 * The pipeline must report ZERO findings.
 */
int factorial(int n) {
    int result;

    result = 1;
    for (int i = 1; i <= n; i = i + 1) {
        result = result * i;
    }
    return result;
}

int main() {
    int values[3];
    int total;

    values[0] = 2;
    values[1] = 3;
    values[2] = 4;
    total = factorial(values[2]) + values[0];

    return total;
}
