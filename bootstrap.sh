DIR=~/.dotfiles

# install git
sudo apt-get install -y git > /dev/null

# clone into dotfiles directory
git clone --recursive https://github.com/zsalzbank/dotfiles.git $DIR > /dev/null

# install dotfiles
pushd $DIR > /dev/null
make
popd > /dev/null
