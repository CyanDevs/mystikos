sudo rm -rf $(git ls-files --others --directory)
make distclean
make -j3 world
