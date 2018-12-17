## Code Review Checklist
Code reviewers should verify the following before merging a pull request:

  * Code matches the lab coding style
     * New code matches [PEP8 standards](https://www.python.org/dev/peps/pep-0008/)
     * Existing surrounding code (e.g. the rest of a function) is updated to match PEP8 if it doesn't already

  * Code has [adequate test coverage](#tests). In short:
     * Bug fixes should include tests that would have caught the bug, to prevent regressions
     * Parts of the code with core logic / very complex logic should usually have tests
     * Code likely to be reused should usually have tests

  * Documentation is updated as needed
    * For datman bin scripts: a doc string (or descriptive comment in the case of bash) exists and is up to date. It should contain:
      * a short description of what the script does
      * an example of usage
      * references to any papers it implements algorithms from
      * A section detailing any configuration, environment variables, and dependencies needed to run
    * Anything that introduces a change to the datman config files should include an update to [this wiki page.](https://github.com/TIGRLab/datman/wiki/Datman-Config)
    * Anything that introduces a change to the nightly pipelines or how they're run (modifying dependencies, environment variables needed, etc.) should include an update to [this page.](https://github.com/TIGRLab/documentation/wiki/Nightly-Pipelines)

  * Code is readable
    * Variables and functions use descriptive names. If a single letter variable must be used it should only be needed for a few lines of code around initial assignment, e.g. for very short loops or a list comprehension.
    * Where possible, comments explaining what a block of code is doing should be replaced with a descriptively named function
    * Non-obvious design decisions and complicated expressions (e.g. regexs) should be explained with a comment
    * Old code should be deleted instead of commented out. 

  * Dependencies are necessary and added to requirements
    * Any changes to the dependencies (removal, addition, updated versions) should come with an update to requirements.txt and the packages.module virtual environment.
    * A new package should not be added just to save on a few lines of code. Make sure the code really needs it before adding something new. 
    * If a pull request is attempting to replace an old dependency with a new, more featureful one, it must update old code and completely strip the old dependency

  * Duplication is minimized
    * If a piece of code is used twice or more, it should probably be refactored into a function
    * If a piece of code is used between different scripts it should be moved into an importable library inside the repo or added to utils and imported in
    * If a piece of code duplicates some existing functionality it should be replaced with the existing function/class before merging 

## Tests
Currently we use python 2's built in library `unittest` for our unit tests. We use the `nose` package to run them, and use the `mock` package for mocks. 

**Be aware**: in python 3 mock is built into unittest. Python 2.7's mock version 2.0.0 is a rolling backport of python 3's version though, so py3 mock tutorials and documentation should be relevant and accurate for python 2.7's version except that the import statement will be `import mock` instead of `import unittest.mock`.

### Coverage Requirements
This is a bit tricky. [This has been circulating the web for a while](https://stackoverflow.com/a/90021) in answer to the question "How much test coverage do I need". The truth is it's something you learn with experience. 

There are a couple rules of thumb though:
- If you fix a bug, you should almost definitely add a test case that would have failed in the presence of that bug. This helps prevent regressions and documents what may have been a non-obvious edge case.
- If a part of the code implements some core logic or very complicated logic you should probably add a few test cases
- If a part of the code will be highly reused it's probably worth adding enough test cases to document that it handles edge cases correctly and that it just generally behaves as expected.

### Running tests
To run all tests use:
```
nosetests ${path_to_datman}/tests/
```
To run tests for only a specific script use:
```
nosetests ${path_to_datman}/tests/test_${script_name}
```

### Help and Documentation
[This article](https://www.toptal.com/qa/how-to-write-testable-code-and-why-it-matters) gives a good overview of software testing. [This article](https://jeffknupp.com/blog/2013/12/09/improve-your-python-understanding-unit-testing/) gives more info about testing in python and [this one](http://docs.python-guide.org/en/latest/writing/tests/) gives some good general advice. [This page](https://docs.python.org/dev/library/unittest.mock.html) contains docs for the py3 version of mock. If more info / help is needed please see Dawn :) 
