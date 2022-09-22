.. include:: links.rst

----------------------
Contributing to Datman
----------------------

Contributions from anyone are very welcome! Below are some helpful guidelines 
to follow when opening a pull request to maximize the chances that it is 
accepted without a request for changes:

* Give your PR a correctly formatted title. Your title should be prefixed 
  with a tag that tells us (and our automated changelog builder) what type 
  of change your PR applies. 
  
  Correctly formatted tags look like ``[TAG]`` or ``tag:``. If your PR 
  introduces breaking changes (i.e. changes that may break code that uses datman)
  you can use an exclamation mark before the colon with the second tag format
  indicate this: ``tag!:``
  
  Tags aren't case-sensitive. Below is a complete list of accepted tags:
  
    * ``[ENH]`` or ``enh:`` or ``feat:`` for pull requests that add new features
    * ``[FIX]`` or ``fix:`` for pull requests that fix bugs
    * ``[REF]`` or ``ref:`` for pull requests that refactor code
    * ``[TEST]`` or ``test:`` for pull requests that add or update tests
    * ``[DOC]`` or ``doc:`` for pull requests that update documentation
    * ``[DEP]`` or ``dep:`` for pull requests that update dependencies
    * ``[IGNORE]`` or ``ignore:`` for pull requests that should be omitted from
      release change logs.

* Follow `PEP8 standards <https://www.python.org/dev/peps/pep-0008/>`_ and 
  try to write code that is readable for other people. You can check 
  your PEP8 compliance and find some common readability issues using the 
  commands below. 
  
  .. code-block:: bash
  
    # Run these commands inside the datman folder
    
    # Install additional packages needed to check for style issues.
    pip install .[style]
    
    # Check for PEP8 issues.
    flake8 <path to your code here>
    
    # Check for common style issues.
    pylint <path to your code here>
    
* Ensure existing tests will continue to pass after your changes are applied.
  If any of our tests are no longer relevant after your changes, please update or 
  remove them. 
  
  .. code-block:: bash
  
    # Run these commands inside the datman folder
    
    # Install additional packages needed to run tests
    pip install .[test]
    
    # Run all datman tests
    pytest tests/
    
* Add unit tests whenever possible. We use `pytest <https://docs.pytest.org>`_ 
  for our unit tests, please use it when writing new tests.
  
* Before adding a new package dependency to datman please ensure it is
  actually necessary.
  
    * Any changes to the dependencies (removal, addition, updated versions) 
      should come with an update to the dependencies or optional-dependencies
      in datman's ``pyproject.toml`` file.
      
    * If your pull request is attempting to replace an old dependency with a new, 
      more featureful one, you should update old code to completely strip the 
      old dependency from datman.
