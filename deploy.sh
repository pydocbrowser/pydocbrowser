tar cf - -C dist . | ssh pydoc.dev 'sh -c "set -x; cd /var/www/pydoc.dev && rm -r * && pwd && tar xvf - && echo done"'
