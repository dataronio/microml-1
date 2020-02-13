import os
import signal
import subprocess
import tempfile

from microml import exceptions, parser, typing

PRELUDE = """
#include <stdio.h>

int print(int in) {
    printf("%d\\n", in);
    return 0;
}
"""


class Compiler:
    def __init__(self, interactive=True):
        self.interactive = interactive
        self.p = parser.Parser()
        self.equations = []
        self.symtab = {"print": typing.Func([typing.Int()], typing.Int())}
        self.code = []
        self.main = -1
        self.unifier = None

    def compile(self, source):
        parsed, pos = self.p.parse(source, self.interactive)

        if parsed.name in self.symtab:
            print("Warning! Redefining {}!".format(parsed.name))

        self.symtab = {
            **self.symtab,
            **typing.assign_typenames(parsed.expr, self.symtab),
        }
        self.equations.extend(typing.generate_equations(parsed.expr))
        self.unifier = typing.unify_equations(self.equations)
        t = typing.get_expression_type(parsed.expr.typ, self.unifier)

        if self.interactive:
            print("{} :: {}".format(parsed, t))

        self.symtab[parsed.name] = t

        if parsed.name == "main":
            self.main = len(self.code)

        self.code.append(parsed)

        return pos

    def get_type(self):
        return lambda x: typing.get_expression_type(x, self.unifier)

    def interpret(self):
        class Printr:
            def eval(self, env, arg):
                print(arg[0])

        env = {"print": Printr()}
        for node in self.code:
            node.eval(env)
        if "main" in env:
            try:
                env["main"].eval(env, [])
            except Exception as e:
                raise exceptions.MLEvalException(str(e))

    def execute(self):
        if self.code == []:
            raise exceptions.MLCompilerException("Nothing to execute!")
        if self.main == -1:
            raise exceptions.MLCompilerException("No `main` function specified!")

        main_node = self.code[self.main]
        compiled = "{}\n{}\n{}".format(
            PRELUDE,
            "\n".join(
                node.compile(self.get_type())
                for node in self.code
                if node.name != "main"
            ),
            main_node.compile(self.get_type()),
        )

        cc = os.getenv("CC", "gcc")

        _, i = tempfile.mkstemp()
        _, o = tempfile.mkstemp()
        i = "{}.c".format(i)
        with open(i, "w+") as f:
            f.write(compiled)

        try:
            print(subprocess.check_output([cc, i, "-o", o]).decode("utf-8"), end="")
        except subprocess.CalledProcessError as e:
            raise exceptions.MLCompilerException(str(e))

        try:
            print(subprocess.check_output([o]).decode("utf-8"), end="")
        except subprocess.CalledProcessError as e:
            code = e.returncode
            if code < 0:
                raise exceptions.MLCompilerException(
                    "Running the executable failed with signal {}!".format(
                        signal.Signals(-code).name
                    )
                )
            raise exceptions.MLCompilerException(
                "Running the executable failed with exit code {}!".format(code)
            )
