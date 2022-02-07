tar cf - -C dist . | ssh pydoc.dev 'sh -c "
set -x &&
cd /var/www/pydoc.dev &&
([ ! -d tmp ] || rm -r tmp) &&
mkdir tmp &&
tar xvf - -C tmp &&
([ ! -d dist ] || mv dist old) &&
mv tmp dist &&
rm -r old
"'
