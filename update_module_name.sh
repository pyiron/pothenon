#!/bin/bash
# Mac users: You [may first need to install gnu-sed](https://github.com/MigleSur/GenAPI/issues/8)

set -eu # exit script immediately on any error (e) and if used vars are unset (u)
set -o pipefail # exit directly if pipeline fails anywhere and don't continue to next command

module_name="pyiron_IntendedModuleName"

replace_and_log() {
  local from="$1"
  local to="$2"
  local file="$3"
  local count

  if grep -qF -- "$from" "$file"; then
    count=$(grep -oF -- "$from" "$file" | wc -l)
    printf 'Replacing "%s" with "%s" in %s (%s occurrence(s))\n' \
      "$from" "$to" "$file" "$count"
  fi

  sed -i "s/${from}/${to}/g" "$file"
}

for file in .binder/postBuild \
            .github/ISSUE_TEMPLATE/*.md \
            docs/conf.py \
            docs/index.rst \
            notebooks/example.ipynb \
            tests/unit/test_tests.py \
            .coveragerc \
            .gitattributes \
            MANIFEST.in \
            pyproject.toml
do
  replace_and_log "pyiron_module_template" "${module_name}" "${file}"
done


git mv pyiron_module_template ${module_name}

rm update_module_name.sh
