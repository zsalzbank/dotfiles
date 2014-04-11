DIR=~/.dotfiles

# install git
sudo apt-get install -y git

# clone into dotfiles directory
git clone https://github.com/zsalzbank/dotfiles.git $DIR

# install dotfiles
pushd $DIR
make
popd
