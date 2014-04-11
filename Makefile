install: install-git install-vim done

install-git:
	@echo "installing git settings..."
	@ln -sf `pwd`/git/gitconfig ~/.gitconfig

install-vim:
	@echo "installing vim settings..."
	@rm -rf ~/.vim ~/.vimrc
	@ln -sf `pwd`/vim ~/.vim
	@ln -sf ~/.vim/vimrc ~/.vimrc
	@mkdir -p ~/.vim/autoload
	@curl -Sso ~/.vim/autoload/pathogen.vim \
		https://raw.github.com/tpope/vim-pathogen/master/autoload/pathogen.vim

done:
	@echo "done installing dotfiles!"
