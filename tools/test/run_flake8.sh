#!/bin/bash -u
root=`dirname $0`
num_files_checked=0
num_errors_found=0

echo "INFO: starting flake8 tests"
files_to_check=($(git ls-files '*.py'| grep -v fake_data_root))
files_to_check+=($(git ls-files --others --exclude-standard '*.py'| \
                    grep -v fake_data_root))
for f in ${files_to_check[@]}; do
    if `file $f| grep -q "Python script"`; then
        flake8 $f
        if (($?)); then
            num_errors_found=$((num_errors_found + 1))
        fi
        num_files_checked=$((num_files_checked + 1))
    fi
done

echo -e "INFO: $num_files_checked python files checked with flake8. \
$num_errors_found file(s) found with errors."
if ((num_errors_found)); then
    exit 1
else
    exit 0
fi
